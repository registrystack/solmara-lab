import type { Cookies } from '@sveltejs/kit';
import { createPrivateKey, webcrypto } from 'node:crypto';
import * as oidc from 'openid-client';
import type { PortalSession } from './session';

const AUTH_PROVIDER_ENV = 'PORTAL_AUTH_PROVIDER';
export const ESIGNET_LOGIN_COOKIE = 'solmara_esignet_login';
const LOGIN_MAX_AGE_SECONDS = 10 * 60;
export const MAX_PENDING_ESIGNET_LOGINS = 1000;

type StoredLogin = {
  verifier: string;
  nonce: string;
  redirectUri: string;
  issuer: string;
  clientId: string;
  expiresAt: number;
};

export type EsignetConfig = {
  issuer: string;
  transportOrigin?: string;
  allowHttp: boolean;
  clientId: string;
  clientKeyId: string;
  clientPrivateKeyPem: string;
  redirectUri: string;
  scope: string;
  subjectClaim: string;
  secureCookies: boolean;
};

export class EsignetConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'EsignetConfigError';
  }
}

export class EsignetAuthError extends Error {
  constructor(message: string, readonly stage = 'validation', readonly code?: string) {
    super(message);
    this.name = 'EsignetAuthError';
  }
}

// This lab runs one portal process. Pending logins expire and have a hard cap.
const loginStates = new Map<string, StoredLogin>();

export function esignetConfigFor(url: URL, env: NodeJS.ProcessEnv = process.env): EsignetConfig | null {
  const provider = env[AUTH_PROVIDER_ENV] ?? 'mock';
  if (provider === 'mock') return null;
  if (provider !== 'esignet') {
    throw new EsignetConfigError(`${AUTH_PROVIDER_ENV} must be "mock" or "esignet"`);
  }
  const allowHttp = env.PORTAL_ESIGNET_ALLOW_HTTP === 'true';
  const issuer = trustedUrl(env.PORTAL_ESIGNET_ISSUER, 'PORTAL_ESIGNET_ISSUER', allowHttp);
  const transport = env.PORTAL_ESIGNET_TRANSPORT_ORIGIN
    ? trustedUrl(env.PORTAL_ESIGNET_TRANSPORT_ORIGIN, 'PORTAL_ESIGNET_TRANSPORT_ORIGIN', allowHttp)
    : undefined;
  if (transport && new URL(transport).pathname !== '/') {
    throw new EsignetConfigError('PORTAL_ESIGNET_TRANSPORT_ORIGIN must be an origin without a path');
  }
  return {
    issuer,
    transportOrigin: transport,
    allowHttp,
    clientId: env.PORTAL_ESIGNET_CLIENT_ID || 'solmara-portal',
    clientKeyId: env.PORTAL_ESIGNET_CLIENT_KEY_ID || 'solmara-portal-key-1',
    clientPrivateKeyPem: privateKeyFromEnv(env),
    redirectUri: trustedUrl(env.PORTAL_ESIGNET_REDIRECT_URI || new URL('/auth/callback', url.origin).href,
      'PORTAL_ESIGNET_REDIRECT_URI', allowHttp),
    scope: env.PORTAL_ESIGNET_SCOPE || 'openid',
    subjectClaim: env.PORTAL_ESIGNET_SUBJECT_CLAIM || 'individual_id',
    secureCookies: env.PORTAL_SECURE_COOKIES === 'true'
  };
}

export async function createEsignetLogin(
  cookies: Cookies, config: EsignetConfig, fetchFn: typeof fetch = fetch
): Promise<URL> {
  reclaimExpiredLogins();
  const previous = cookies.get(ESIGNET_LOGIN_COOKIE);
  if (previous) loginStates.delete(previous);
  if (loginStates.size >= MAX_PENDING_ESIGNET_LOGINS) {
    throw new EsignetAuthError('eSignet login capacity reached');
  }
  const client = await discover(config, fetchFn);
  const state = oidc.randomState();
  const verifier = oidc.randomPKCECodeVerifier();
  const nonce = oidc.randomNonce();
  const authorize = oidc.buildAuthorizationUrl(client, {
    response_type: 'code', redirect_uri: config.redirectUri, scope: config.scope, ui_locales: 'en',
    claims: JSON.stringify({ userinfo: {
      given_name: null, family_name: null, [config.subjectClaim]: { essential: true }
    } }),
    state, nonce, code_challenge: await oidc.calculatePKCECodeChallenge(verifier),
    code_challenge_method: 'S256'
  });
  // Discovery is asynchronous, so enforce the bound again immediately before insertion.
  if (loginStates.size >= MAX_PENDING_ESIGNET_LOGINS) {
    throw new EsignetAuthError('eSignet login capacity reached');
  }
  loginStates.set(state, {
    verifier, nonce, redirectUri: config.redirectUri, issuer: config.issuer,
    clientId: config.clientId, expiresAt: Date.now() + LOGIN_MAX_AGE_SECONDS * 1000
  });
  cookies.set(ESIGNET_LOGIN_COOKIE, state, {
    path: '/', httpOnly: true, sameSite: 'lax', secure: config.secureCookies,
    maxAge: LOGIN_MAX_AGE_SECONDS
  });
  return authorize;
}

export async function completeEsignetLogin(
  cookies: Cookies, url: URL, config: EsignetConfig, fetchFn: typeof fetch = fetch
): Promise<PortalSession> {
  const { login, state } = consumeLogin(cookies, url, config);
  let stage = 'discovery';
  try {
    const client = await discover(config, fetchFn);
    stage = 'token';
    const token = await oidc.authorizationCodeGrant(client, url, {
      pkceCodeVerifier: login.verifier, expectedState: state,
      expectedNonce: login.nonce, idTokenExpected: true
    });
    const identity = token.claims();
    if (!identity) throw new EsignetAuthError('eSignet token response omitted ID token');
    stage = 'userinfo';
    const claims = await oidc.fetchUserInfo(client, token.access_token, identity.sub);
    return sessionFromClaims(claims, config);
  } catch (err) {
    if (err instanceof EsignetAuthError || err instanceof EsignetConfigError) throw err;
    // Protocol errors can contain tokens and provider response bodies. Keep them server-private.
    const code = err instanceof Error && 'code' in err && typeof err.code === 'string' &&
      /^OAUTH_[A-Z_]{1,60}$/.test(err.code) ? err.code : undefined;
    throw new EsignetAuthError('eSignet authentication validation failed', stage, code);
  }
}

async function discover(config: EsignetConfig, fetchFn: typeof fetch): Promise<oidc.Configuration> {
  try {
    const key = createPrivateKey(config.clientPrivateKeyPem);
    const privateKey = await webcrypto.subtle.importKey('pkcs8',
      key.export({ type: 'pkcs8', format: 'der' }),
      { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
    const client = await oidc.discovery(new URL(config.issuer), config.clientId, {
      token_endpoint_auth_method: 'private_key_jwt',
      id_token_signed_response_alg: 'PS256', userinfo_signed_response_alg: 'PS256'
    }, oidc.PrivateKeyJwt({ key: privateKey, kid: config.clientKeyId }), {
      timeout: 15,
      // Signature verification is required even on the explicitly configured local HTTP transport.
      execute: [oidc.enableNonRepudiationChecks, ...(config.allowHttp ? [oidc.allowInsecureRequests] : [])],
      [oidc.customFetch]: async (input, init) => {
        const endpoint = new URL(input);
        if (endpoint.origin !== new URL(config.issuer).origin) {
          throw new EsignetConfigError('eSignet server endpoint must use the trusted issuer origin');
        }
        if (config.transportOrigin) {
          const transport = new URL(config.transportOrigin);
          endpoint.protocol = transport.protocol;
          endpoint.host = transport.host;
        }
        const body = init.body instanceof Uint8Array ? new Uint8Array(init.body) : init.body;
        return fetchFn(endpoint, { ...init, body, redirect: 'error' });
      }
    });
    // Keep the configured issuer string exact, including path and trailing slash.
    if (client.serverMetadata().issuer !== config.issuer) {
      throw new EsignetConfigError('eSignet discovery issuer mismatch');
    }
    return client;
  } catch (err) {
    if (err instanceof EsignetConfigError) throw err;
    throw new EsignetAuthError('eSignet discovery failed', 'discovery');
  }
}

export function resetEsignetLoginStates(): void {
  loginStates.clear();
}

export function reclaimExpiredLogins(now = Date.now()): number {
  let reclaimed = 0;
  for (const [state, login] of loginStates) {
    if (login.expiresAt <= now) {
      loginStates.delete(state);
      reclaimed += 1;
    }
  }
  return reclaimed;
}

function trustedUrl(value: string | undefined, name: string, allowHttp: boolean): string {
  if (!value) throw new EsignetConfigError(`${name} is required when ${AUTH_PROVIDER_ENV}=esignet`);
  try {
    const url = new URL(value);
    if ((url.protocol !== 'https:' && !(allowHttp && url.protocol === 'http:')) ||
      url.username || url.password || url.search || url.hash) throw new Error('invalid URL');
    return value;
  } catch {
    throw new EsignetConfigError(`${name} must be an absolute HTTPS URL (local HTTP requires PORTAL_ESIGNET_ALLOW_HTTP=true)`);
  }
}

function privateKeyFromEnv(env: NodeJS.ProcessEnv): string {
  const encoded = env.PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64;
  if (!encoded) throw new EsignetConfigError('PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64 is required');
  try {
    const pem = Buffer.from(encoded, 'base64').toString('utf8');
    const key = createPrivateKey(pem);
    if (key.asymmetricKeyType !== 'rsa' || (key.asymmetricKeyDetails?.modulusLength ?? 0) < 2048) {
      throw new Error('expected RSA key');
    }
    return pem;
  } catch {
    throw new EsignetConfigError('PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64 must contain a base64-encoded RSA PEM key of at least 2048 bits');
  }
}

function consumeLogin(cookies: Cookies, url: URL, config: EsignetConfig): { login: StoredLogin; state: string } {
  reclaimExpiredLogins();
  const state = url.searchParams.get('state');
  const cookieState = cookies.get(ESIGNET_LOGIN_COOKIE);
  const login = cookieState ? loginStates.get(cookieState) : undefined;
  cookies.delete(ESIGNET_LOGIN_COOKIE, { path: '/' });
  if (cookieState) loginStates.delete(cookieState);
  if (!state || state !== cookieState || url.searchParams.getAll('state').length !== 1) {
    throw new EsignetAuthError('invalid eSignet callback state', 'state');
  }
  if (!login || login.redirectUri !== config.redirectUri || login.issuer !== config.issuer ||
    login.clientId !== config.clientId) throw new EsignetAuthError('expired eSignet login state', 'pending-login');
  const expected = new URL(login.redirectUri);
  if (url.origin !== expected.origin || url.pathname !== expected.pathname) {
    throw new EsignetAuthError('invalid eSignet callback URI', 'callback-uri');
  }
  return { login, state };
}

function sessionFromClaims(claims: Record<string, unknown>, config: EsignetConfig): PortalSession {
  const subject = stringClaim(claims, config.subjectClaim);
  if (!subject) {
    throw new EsignetAuthError(`eSignet UserInfo omitted configured subject claim ${config.subjectClaim}`, 'session');
  }
  return {
    subject,
    displayName:
      stringClaim(claims, 'name') ||
      [stringClaim(claims, 'given_name'), stringClaim(claims, 'family_name')].filter(Boolean).join(' ') ||
      subject
  };
}


function stringClaim(claims: Record<string, unknown>, name: string): string | null {
  const value = claims[name];
  return typeof value === 'string' && value.trim() ? value : null;
}
