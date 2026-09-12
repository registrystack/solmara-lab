// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Cookies } from '@sveltejs/kit';
import { constants, createHash, generateKeyPairSync, sign, verify } from 'node:crypto';
import {
  completeEsignetLogin, createEsignetLogin, esignetConfigFor, ESIGNET_LOGIN_COOKIE,
  resetEsignetLoginStates, reclaimExpiredLogins, MAX_PENDING_ESIGNET_LOGINS, type EsignetConfig
} from './esignet';
import { GET as loginRoute } from '../../routes/auth/login/+server';
import { GET as callbackRoute } from '../../routes/auth/callback/+server';
import { getSession } from './session';

class MemoryCookies {
  readonly values = new Map<string, string>();
  get(name: string) { return this.values.get(name); }
  set(name: string, value: string) { this.values.set(name, value); }
  delete(name: string) { this.values.delete(name); }
  asCookies(): Cookies {
    // The routes only use get, set and delete on SvelteKit's cookie interface.
    return this as unknown as Cookies;
  }
}

const clientKey = generateKeyPairSync('rsa', { modulusLength: 2048 });
const issuerKey = generateKeyPairSync('rsa', { modulusLength: 2048 });
const cfg: EsignetConfig = {
  issuer: 'https://esignet.example.test', allowHttp: false,
  clientId: 'solmara-portal', clientKeyId: 'solmara-portal-key-1',
  clientPrivateKeyPem: clientKey.privateKey.export({ type: 'pkcs8', format: 'pem' }).toString(),
  redirectUri: 'https://portal.example.test/auth/callback', scope: 'openid',
  subjectClaim: 'individual_id', secureCookies: true
};
const metadata = {
  issuer: cfg.issuer, authorization_endpoint: `${cfg.issuer}/oauth2/authorize`,
  token_endpoint: `${cfg.issuer}/oauth2/token`, userinfo_endpoint: `${cfg.issuer}/oauth2/userinfo`,
  jwks_uri: `${cfg.issuer}/oauth2/jwks`, response_types_supported: ['code'],
  subject_types_supported: ['public'], id_token_signing_alg_values_supported: ['PS256'],
  userinfo_signing_alg_values_supported: ['PS256'], token_endpoint_auth_methods_supported: ['private_key_jwt']
};

function jwt(claims: Record<string, unknown>, tampered = false): string {
  const header = Buffer.from(JSON.stringify({ alg: 'PS256', kid: 'issuer-key' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify(claims)).toString('base64url');
  const signature = sign('RSA-SHA256', Buffer.from(`${header}.${payload}`), { key: issuerKey.privateKey, padding: constants.RSA_PKCS1_PSS_PADDING, saltLength: 32 }).toString('base64url');
  return `${header}.${payload}.${tampered ? (signature[0] === 'A' ? 'B' : 'A') + signature.slice(1) : signature}`;
}
function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } });
}

type Options = {
  id?: Record<string, unknown>; userinfo?: Record<string, unknown>;
  tamperId?: boolean; tamperUserinfo?: boolean; unsignedUserinfo?: boolean;
  omitId?: boolean; tokenError?: boolean; metadata?: Record<string, unknown>;
  jwksAlgorithm?: string;
};
function provider(options: Options = {}) {
  let nonce = '';
  let tokenBody = new URLSearchParams();
  const fetchFn = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : input);
    if (url.pathname === '/.well-known/openid-configuration') return json({ ...metadata, ...options.metadata });
    if (url.pathname === '/oauth2/jwks') {
      return json({ keys: [{ ...issuerKey.publicKey.export({ format: 'jwk' }), kid: 'issuer-key', alg: options.jwksAlgorithm ?? 'PS256', use: 'sig' }] });
    }
    const now = Math.floor(Date.now() / 1000);
    const common = { iss: cfg.issuer, aud: cfg.clientId, sub: 'pairwise-subject', iat: now, exp: now + 300 };
    if (url.pathname === '/oauth2/token') {
      tokenBody = new URLSearchParams(init?.body?.toString());
      if (options.tokenError) return json({ error: 'invalid_grant' }, 400);
      return json({ access_token: 'access-token', token_type: 'Bearer',
        ...(options.omitId ? {} : { id_token: jwt({ ...common, nonce, ...options.id }, options.tamperId) }) });
    }
    if (url.pathname === '/oauth2/userinfo') {
      expect(new Headers(init?.headers).get('authorization')).toBe('Bearer access-token');
      const claims = { ...common, individual_id: '8fa0e667-5042-5ba2-9837-a9fd852f0394', name: 'Elena Dela Cruz', ...options.userinfo };
      return options.unsignedUserinfo ? json(claims) : new Response(jwt(claims, options.tamperUserinfo), {
        headers: { 'content-type': 'application/jwt' }
      });
    }
    throw new Error('Unexpected OIDC request');
  });
  return { fetchFn, tokenBody: () => tokenBody, setNonce: (value: string) => { nonce = value; } };
}
async function begin(options: Options = {}, config = cfg) {
  const jar = new MemoryCookies();
  const server = provider(options);
  const authorize = await createEsignetLogin(jar.asCookies(), config, server.fetchFn);
  server.setNonce(authorize.searchParams.get('nonce') ?? '');
  const callback = new URL(config.redirectUri);
  callback.searchParams.set('code', 'one-use-code');
  callback.searchParams.set('state', authorize.searchParams.get('state') ?? '');
  return { jar, server, authorize, callback,
    complete: () => completeEsignetLogin(jar.asCookies(), callback, config, server.fetchFn) };
}

describe('eSignet portal login', () => {
  beforeEach(() => { resetEsignetLoginStates(); });
  afterEach(() => { resetEsignetLoginStates(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('verifies a signed login and sends PKCE plus a valid private_key_jwt assertion', async () => {
    const flow = await begin();
    expect(flow.authorize.pathname).toBe('/oauth2/authorize');
    expect(flow.authorize.searchParams.get('scope')).toBe('openid');
    expect(flow.authorize.searchParams.get('ui_locales')).toBe('en');
    expect(JSON.parse(flow.authorize.searchParams.get('claims') ?? '{}')).toEqual({
      userinfo: { given_name: null, family_name: null, individual_id: { essential: true } }
    });
    expect(flow.jar.get(ESIGNET_LOGIN_COOKIE)).toBe(flow.authorize.searchParams.get('state'));
    expect(await flow.complete()).toEqual({ subject: '8fa0e667-5042-5ba2-9837-a9fd852f0394', displayName: 'Elena Dela Cruz' });
    const body = flow.server.tokenBody();
    expect(body.get('grant_type')).toBe('authorization_code');
    expect(body.get('redirect_uri')).toBe(cfg.redirectUri);
    expect(body.get('client_assertion_type')).toBe('urn:ietf:params:oauth:client-assertion-type:jwt-bearer');
    expect(createHash('sha256').update(body.get('code_verifier') ?? '').digest('base64url'))
      .toBe(flow.authorize.searchParams.get('code_challenge'));
    const [header, payload, signature] = (body.get('client_assertion') ?? '').split('.');
    expect(verify('RSA-SHA256', Buffer.from(`${header}.${payload}`), clientKey.publicKey, Buffer.from(signature, 'base64url'))).toBe(true);
    expect(JSON.parse(Buffer.from(header, 'base64url').toString())).toMatchObject({ alg: 'RS256', kid: cfg.clientKeyId });
    expect(JSON.parse(Buffer.from(payload, 'base64url').toString())).toMatchObject({ iss: cfg.clientId, sub: cfg.clientId });
    expect(flow.jar.get(ESIGNET_LOGIN_COOKIE)).toBeUndefined();
    await expect(flow.complete()).rejects.toThrow('callback state');
    expect(flow.server.fetchFn.mock.calls.filter(([url]) => url.toString().endsWith('/token'))).toHaveLength(1);
  });

  it.each<[string, Options]>([
    ['ID token signature', { tamperId: true }],
    ['verification key algorithm mismatch', { jwksAlgorithm: 'RS256' }],
    ['ID token issuer', { id: { iss: 'https://attacker.example.test' } }],
    ['ID token audience', { id: { aud: 'another-client' } }],
    ['ID token nonce', { id: { nonce: 'another-login' } }],
    ['ID token expiry', { id: { exp: 1 } }],
    ['missing ID token', { omitId: true }],
    ['UserInfo signature', { tamperUserinfo: true }],
    ['UserInfo issuer', { userinfo: { iss: 'https://attacker.example.test' } }],
    ['UserInfo audience', { userinfo: { aud: 'another-client' } }],
    ['UserInfo subject correlation', { userinfo: { sub: 'different-subject' } }],
    ['unsigned UserInfo', { unsignedUserinfo: true }],
    ['missing identity claim', { userinfo: { individual_id: null } }],
    ['token endpoint refusal', { tokenError: true }]
  ])('rejects %s and consumes the login even on failure', async (_name, options) => {
    const flow = await begin(options);
    await expect(flow.complete()).rejects.toThrow();
    await expect(flow.complete()).rejects.toThrow('callback state');
    expect(flow.server.fetchFn.mock.calls.filter(([url]) => url.toString().endsWith('/token'))).toHaveLength(1);
  });

  it('rejects wrong, duplicate, expired and cross-client state before token exchange', async () => {
    for (const scenario of ['wrong', 'duplicate', 'expired', 'client', 'uri']) {
      const flow = await begin();
      if (scenario === 'wrong') flow.callback.searchParams.set('state', 'wrong');
      if (scenario === 'duplicate') flow.callback.searchParams.append('state', 'second');
      if (scenario === 'expired') reclaimExpiredLogins(Date.now() + 601_000);
      if (scenario === 'uri') flow.callback.pathname = '/wrong';
      await expect(completeEsignetLogin(flow.jar.asCookies(), flow.callback,
        scenario === 'client' ? { ...cfg, clientId: 'changed' } : cfg, flow.server.fetchFn)).rejects.toThrow();
      expect(flow.server.fetchFn.mock.calls.some(([url]) => url.toString().endsWith('/token'))).toBe(false);
    }
  });

  it('consumes a refused authorization callback without exchanging a code', async () => {
    const flow = await begin();
    flow.callback.searchParams.delete('code');
    flow.callback.searchParams.set('error', 'access_denied');
    await expect(flow.complete()).rejects.toThrow();
    await expect(flow.complete()).rejects.toThrow('callback state');
    expect(flow.server.fetchFn.mock.calls.some(([url]) => url.toString().endsWith('/token'))).toBe(false);
  });

  it('rejects an inferred callback scheme that differs from the registered public origin', async () => {
    const flow = await begin();
    flow.callback.protocol = 'http:';
    await expect(flow.complete()).rejects.toMatchObject({ stage: 'callback-uri' });
    expect(flow.server.fetchFn.mock.calls.some(([url]) => url.toString().endsWith('/token'))).toBe(false);
    await expect(flow.complete()).rejects.toMatchObject({ stage: 'state' });
  });

  it('requires an exact trusted discovery issuer, including trailing slash', async () => {
    for (const issuer of ['https://attacker.example.test', `${cfg.issuer}/`]) {
      const server = provider({ metadata: { issuer } });
      await expect(createEsignetLogin(new MemoryCookies().asCookies(), cfg, server.fetchFn)).rejects.toThrow();
    }
  });

  it('maps only the configured issuer origin to local transport and preserves validation', async () => {
    const flow = await begin({}, { ...cfg, transportOrigin: 'http://esignet:8080', allowHttp: true });
    await expect(flow.complete()).resolves.toMatchObject({ subject: '8fa0e667-5042-5ba2-9837-a9fd852f0394' });
    expect(flow.server.fetchFn.mock.calls.every(([url]) => new URL(url.toString()).origin === 'http://esignet:8080')).toBe(true);
    expect(flow.authorize.origin).toBe(cfg.issuer);
    const untrusted = await begin({ metadata: { token_endpoint: 'https://attacker.example.test/token' } });
    await expect(untrusted.complete()).rejects.toThrow();
    expect(untrusted.server.fetchFn.mock.calls.some(([url]) => url.toString().includes('attacker'))).toBe(false);
  });

  it('bounds pending logins and reclaims expired entries', async () => {
    const server = provider();
    await Promise.all(Array.from({ length: MAX_PENDING_ESIGNET_LOGINS + 1 }, async () => {
      try { await createEsignetLogin(new MemoryCookies().asCookies(), cfg, server.fetchFn); } catch { /* Capacity is expected. */ }
    }));
    await expect(createEsignetLogin(new MemoryCookies().asCookies(), cfg, server.fetchFn)).rejects.toThrow('capacity');
    expect(reclaimExpiredLogins(Date.now() + 601_000)).toBe(MAX_PENDING_ESIGNET_LOGINS);
    await expect(createEsignetLogin(new MemoryCookies().asCookies(), cfg, server.fetchFn)).resolves.toBeInstanceOf(URL);
  });

  it('defaults to openid with only necessary identity and optional display claims while preserving scope overrides', () => {
    const env = {
      PORTAL_AUTH_PROVIDER: 'esignet', PORTAL_ESIGNET_ISSUER: cfg.issuer,
      PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64: Buffer.from(cfg.clientPrivateKeyPem).toString('base64')
    };
    expect(esignetConfigFor(new URL(cfg.redirectUri), env)?.scope).toBe('openid');
    expect(esignetConfigFor(new URL(cfg.redirectUri), { ...env, PORTAL_ESIGNET_SCOPE: 'openid profile' })?.scope)
      .toBe('openid profile');
  });

  it('requires explicit HTTP opt-in and keeps eSignet disabled by default', () => {
    expect(esignetConfigFor(new URL(cfg.redirectUri), {})).toBeNull();
    expect(() => esignetConfigFor(new URL(cfg.redirectUri), {
      PORTAL_AUTH_PROVIDER: 'esignet', PORTAL_ESIGNET_ISSUER: 'http://127.0.0.1:4308'
    })).toThrow('HTTPS');
  });

  it('uses native server fetch to route a verified callback into a session and reject tampering', async () => {
    const diagnostic = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.stubEnv('PORTAL_AUTH_PROVIDER', 'esignet');
    vi.stubEnv('PORTAL_ESIGNET_ISSUER', cfg.issuer);
    vi.stubEnv('PORTAL_ESIGNET_CLIENT_PRIVATE_KEY_B64', Buffer.from(cfg.clientPrivateKeyPem).toString('base64'));
    vi.stubEnv('PORTAL_ESIGNET_REDIRECT_URI', cfg.redirectUri);
    for (const tamperId of [false, true]) {
      const jar = new MemoryCookies();
      const server = provider({ tamperId });
      vi.stubGlobal('fetch', server.fetchFn);
      const eventFetch = vi.fn(() => { throw new Error('browser request context must not reach OIDC'); });
      // These routes consume only cookies and url, not SvelteKit's contextual fetch.
      const event = { cookies: jar.asCookies(), url: new URL('https://portal.example.test/auth/login'), fetch: eventFetch };
      let location = '';
      try { await loginRoute(event as unknown as Parameters<typeof loginRoute>[0]); } catch (error) {
        if (typeof error === 'object' && error && 'location' in error && typeof error.location === 'string') location = error.location;
      }
      const authorize = new URL(location);
      server.setNonce(authorize.searchParams.get('nonce') ?? '');
      event.url = new URL(`${cfg.redirectUri}?code=route-code&state=${authorize.searchParams.get('state')}`);
      // The callback consumes the same two event properties.
      await expect(callbackRoute(event as unknown as Parameters<typeof callbackRoute>[0])).rejects.toMatchObject(tamperId ? { status: 401 } : { status: 302, location: '/services' });
      expect(getSession(jar.asCookies())).toEqual(tamperId ? null : {
        subject: '8fa0e667-5042-5ba2-9837-a9fd852f0394', displayName: 'Elena Dela Cruz'
      });
      expect(eventFetch).not.toHaveBeenCalled();
      if (tamperId) expect(diagnostic).toHaveBeenLastCalledWith('eSignet login rejected', {
        stage: 'token', code: expect.stringMatching(/^OAUTH_[A-Z_]+$/)
      });
    }
  });
});
