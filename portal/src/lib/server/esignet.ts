import type { Cookies } from '@sveltejs/kit';
import { createHash, createPrivateKey, createSign, randomBytes, randomUUID } from 'node:crypto';
import type { PortalSession } from './session';

const AUTH_PROVIDER_ENV = 'PORTAL_AUTH_PROVIDER';
export const ESIGNET_LOGIN_COOKIE = 'solmara_esignet_login';
const LOGIN_MAX_AGE_SECONDS = 10 * 60;
const LOGIN_MAX_AGE_MS = LOGIN_MAX_AGE_SECONDS * 1000;
const CLIENT_ASSERTION_TYPE = 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer';

type StoredLogin = {
  verifier: string;
  nonce: string;
  redirectUri: string;
  expiresAt: number;
};

export type EsignetConfig = {
  issuer: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  clientAssertionAudience: string;
  userinfoEndpoint: string;
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
  constructor(message: string) {
    super(message);
    this.name = 'EsignetAuthError';
  }
}

const loginStates = new Map<string, StoredLogin>();

export function esignetConfigFor(url: URL, env: NodeJS.ProcessEnv = process.env): EsignetConfig | null {
  const provider = env[AUTH_PROVIDER_ENV] ?? 'mock';
  if (provider === 'mock') return null;
  if (provider !== 'esignet') {
    throw new EsignetConfigError(`${AUTH_PROVIDER_ENV} must be "mock" or "esignet"`);
  }

  const redirectUri = env.PORTAL_ESIGNET_REDIRECT_URI || new URL('/auth/callback', url.origin).toString();
  return {
    issuer: requiredIssuer(env, 'PORTAL_ESIGNET_ISSUER'),
    authorizationEndpoint: requiredUrl(env, 'PORTAL_ESIGNET_AUTHORIZATION_ENDPOINT'),
    tokenEndpoint: requiredUrl(env, 'PORTAL_ESIGNET_TOKEN_ENDPOINT'),
    clientAssertionAudience: optionalUrl(env, 'PORTAL_ESIGNET_CLIENT_ASSERTION_AUDIENCE') || requiredUrl(env, 'PORTAL_ESIGNET_TOKEN_ENDPOINT'),
    userinfoEndpoint: requiredUrl(env, 'PORTAL_ESIGNET_USERINFO_ENDPOINT'),
    clientId: env.PORTAL_ESIGNET_CLIENT_ID || 'solmara-portal',
    clientKeyId: env.PORTAL_ESIGNET_CLIENT_KEY_ID || 'solmara-portal-key-1',
    clientPrivateKeyPem: privateKeyFromEnv(env),
    redirectUri,
    scope: env.PORTAL_ESIGNET_SCOPE || 'openid profile',
    subjectClaim: env.PORTAL_ESIGNET_SUBJECT_CLAIM || 'individual_id',
    secureCookies: env.PORTAL_SECURE_COOKIES === 'true'
  };
}

export function createEsignetLogin(cookies: Cookies, config: EsignetConfig): URL {
  reclaimExpiredLogins();
  const state = randomToken();
  const verifier = randomToken();
  const nonce = randomToken();
  loginStates.set(state, {
    verifier,
    nonce,
    redirectUri: config.redirectUri,
    expiresAt: Date.now() + LOGIN_MAX_AGE_MS
  });
  cookies.set(ESIGNET_LOGIN_COOKIE, state, {
    path: '/',
    httpOnly: true,
    sameSite: 'lax',
    secure: config.secureCookies,
    maxAge: LOGIN_MAX_AGE_SECONDS
  });

  const authorize = new URL(config.authorizationEndpoint);
  authorize.searchParams.set('response_type', 'code');
  authorize.searchParams.set('client_id', config.clientId);
  authorize.searchParams.set('redirect_uri', config.redirectUri);
  authorize.searchParams.set('scope', config.scope);
  authorize.searchParams.set('state', state);
  authorize.searchParams.set('nonce', nonce);
  authorize.searchParams.set('code_challenge', pkceChallenge(verifier));
  authorize.searchParams.set('code_challenge_method', 'S256');
  return authorize;
}

export async function completeEsignetLogin(
  cookies: Cookies,
  url: URL,
  config: EsignetConfig,
  fetchFn: typeof fetch
): Promise<PortalSession> {
  const login = consumeLogin(cookies, url, config);
  const token = await exchangeCode(url.searchParams.get('code') ?? '', login, config, fetchFn);
  const claims = await fetchUserInfo(token.accessToken, config, fetchFn);
  return sessionFromClaims(claims, config);
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

function requiredUrl(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name];
  if (!value) throw new EsignetConfigError(`${name} is required when ${AUTH_PROVIDER_ENV}=esignet`);
  try {
    return new URL(value).toString();
  } catch {
    throw new EsignetConfigError(`${name} must be an absolute URL`);
  }
}

function requiredIssuer(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name];
  if (!value) throw new EsignetConfigError(`${name} is required when ${AUTH_PROVIDER_ENV}=esignet`);
  try {
    return normalizeIssuer(value);
  } catch {
    throw new EsignetConfigError(`${name} must be an absolute URL`);
  }
}

function optionalUrl(env: NodeJS.ProcessEnv, name: string): string | null {
  const value = env[name];
  if (!value) return null;
  try {
    return new URL(value).toString();
  } catch {
    throw new EsignetConfigError(`${name} must be an absolute URL`);
  }
}

function normalizeIssuer(value: string): string {
  return new URL(value).toString().replace(/\/$/, '');
}

function privateKeyFromEnv(env: NodeJS.ProcessEnv): string {
  const encoded = env.PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64;
  if (!encoded) {
    throw new EsignetConfigError(
      `PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64 is required when ${AUTH_PROVIDER_ENV}=esignet`
    );
  }
  try {
    const pem = Buffer.from(encoded, 'base64').toString('utf8');
    createPrivateKey(pem);
    return pem;
  } catch {
    throw new EsignetConfigError('PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64 must contain a base64-encoded PEM key');
  }
}

function consumeLogin(cookies: Cookies, url: URL, config: EsignetConfig): StoredLogin {
  reclaimExpiredLogins();
  const state = url.searchParams.get('state');
  const code = url.searchParams.get('code');
  const cookieState = cookies.get(ESIGNET_LOGIN_COOKIE);
  cookies.delete(ESIGNET_LOGIN_COOKIE, { path: '/' });

  if (!code || !state || !cookieState || state !== cookieState) {
    throw new EsignetAuthError('invalid eSignet callback state');
  }
  const login = loginStates.get(state);
  loginStates.delete(state);
  if (!login || login.expiresAt <= Date.now() || login.redirectUri !== config.redirectUri) {
    throw new EsignetAuthError('expired eSignet login state');
  }
  return login;
}

async function exchangeCode(
  code: string,
  login: StoredLogin,
  config: EsignetConfig,
  fetchFn: typeof fetch
): Promise<{ accessToken: string }> {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: login.redirectUri,
    client_id: config.clientId,
    code_verifier: login.verifier,
    client_assertion_type: CLIENT_ASSERTION_TYPE,
    client_assertion: clientAssertion(config)
  });
  const response = await fetchFn(config.tokenEndpoint, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded', accept: 'application/json' },
    body
  });
  if (!response.ok) throw new EsignetAuthError('eSignet token exchange failed');
  const token = (await response.json()) as Record<string, unknown>;
  const accessToken = stringClaim(token, 'access_token');
  if (!accessToken) throw new EsignetAuthError('eSignet token response omitted access_token');
  return { accessToken };
}

async function fetchUserInfo(
  accessToken: string,
  config: EsignetConfig,
  fetchFn: typeof fetch
): Promise<Record<string, unknown>> {
  const response = await fetchFn(config.userinfoEndpoint, {
    headers: { accept: 'application/json, application/jwt', authorization: `Bearer ${accessToken}` }
  });
  if (!response.ok) throw new EsignetAuthError('eSignet UserInfo request failed');
  const text = await response.text();
  const claims = parseUserInfo(text);
  const issuer = stringClaim(claims, 'iss');
  if (issuer) {
    try {
      if (normalizeIssuer(issuer) !== config.issuer) {
        throw new EsignetAuthError('eSignet UserInfo issuer mismatch');
      }
    } catch (err) {
      if (err instanceof EsignetAuthError) throw err;
      throw new EsignetAuthError('eSignet UserInfo issuer mismatch');
    }
  }
  return claims;
}

function sessionFromClaims(claims: Record<string, unknown>, config: EsignetConfig): PortalSession {
  const subject = stringClaim(claims, config.subjectClaim);
  if (!subject) {
    throw new EsignetAuthError(`eSignet UserInfo omitted configured subject claim ${config.subjectClaim}`);
  }
  return {
    subject,
    displayName:
      stringClaim(claims, 'name') ||
      [stringClaim(claims, 'given_name'), stringClaim(claims, 'family_name')].filter(Boolean).join(' ') ||
      subject
  };
}

function clientAssertion(config: EsignetConfig): string {
  const now = Math.floor(Date.now() / 1000);
  const header = base64urlJson({ alg: 'RS256', kid: config.clientKeyId, typ: 'JWT' });
  const payload = base64urlJson({
    iss: config.clientId,
    sub: config.clientId,
    aud: config.clientAssertionAudience,
    jti: randomUUID(),
    iat: now,
    exp: now + 300
  });
  const signingInput = `${header}.${payload}`;
  const signer = createSign('RSA-SHA256');
  signer.update(signingInput);
  const signature = signer.sign(config.clientPrivateKeyPem);
  return `${signingInput}.${base64url(signature)}`;
}

function parseUserInfo(text: string): Record<string, unknown> {
  const trimmed = text.trim();
  if (!trimmed) throw new EsignetAuthError('eSignet UserInfo response was empty');
  if (/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*$/.test(trimmed)) return decodeJwtPayload(trimmed);
  try {
    const value = JSON.parse(trimmed) as unknown;
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('not an object');
    }
    return value as Record<string, unknown>;
  } catch {
    throw new EsignetAuthError('eSignet UserInfo response was not JSON or compact JWT');
  }
}

function decodeJwtPayload(jwt: string): Record<string, unknown> {
  try {
    const payload = jwt.split('.')[1];
    const json = Buffer.from(base64urlToBase64(payload), 'base64').toString('utf8');
    const value = JSON.parse(json) as unknown;
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('not an object');
    }
    return value as Record<string, unknown>;
  } catch {
    throw new EsignetAuthError('eSignet compact JWT payload could not be decoded');
  }
}

function stringClaim(claims: Record<string, unknown>, name: string): string | null {
  const value = claims[name];
  return typeof value === 'string' && value.trim() ? value : null;
}

function pkceChallenge(verifier: string): string {
  return base64url(createHash('sha256').update(verifier).digest());
}

function randomToken(): string {
  return randomBytes(32).toString('base64url');
}

function base64urlJson(value: unknown): string {
  return base64url(Buffer.from(JSON.stringify(value), 'utf8'));
}

function base64url(raw: Buffer): string {
  return raw.toString('base64url');
}

function base64urlToBase64(value: string): string {
  return value.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(value.length / 4) * 4, '=');
}
