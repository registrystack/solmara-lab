import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Cookies } from '@sveltejs/kit';
import { generateKeyPairSync } from 'node:crypto';
import {
  completeEsignetLogin,
  createEsignetLogin,
  esignetConfigFor,
  ESIGNET_LOGIN_COOKIE,
  resetEsignetLoginStates,
  type EsignetConfig
} from './esignet';

class MemoryCookies {
  readonly values = new Map<string, string>();

  get(name: string): string | undefined {
    return this.values.get(name);
  }

  set(name: string, value: string): void {
    this.values.set(name, value);
  }

  delete(name: string): void {
    this.values.delete(name);
  }
}

function cookiesForTest(jar: MemoryCookies): Cookies {
  return jar as unknown as Cookies;
}

function privateKeyPem(): string {
  const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  return privateKey.export({ type: 'pkcs8', format: 'pem' }).toString();
}

function config(): EsignetConfig {
  return {
    issuer: 'https://esignet.example.test',
    authorizationEndpoint: 'https://esignet-ui.example.test/authorize',
    tokenEndpoint: 'https://esignet.example.test/v1/esignet/oauth/v2/token',
    clientAssertionAudience: 'https://esignet.example.test/v1/esignet/oauth/v2/token',
    userinfoEndpoint: 'https://esignet.example.test/v1/esignet/oidc/userinfo',
    clientId: 'solmara-portal',
    clientKeyId: 'solmara-portal-key-1',
    clientPrivateKeyPem: privateKeyPem(),
    redirectUri: 'https://portal.example.test/auth/callback',
    scope: 'openid profile',
    subjectClaim: 'individual_id',
    secureCookies: true
  };
}

function callbackUrl(authorizeUrl: URL): URL {
  const state = authorizeUrl.searchParams.get('state');
  expect(state).toBeTruthy();
  return new URL(`https://portal.example.test/auth/callback?code=test-code&state=${state}`);
}

describe('eSignet portal login', () => {
  beforeEach(() => {
    resetEsignetLoginStates();
    vi.useRealTimers();
  });

  afterEach(() => {
    resetEsignetLoginStates();
    vi.useRealTimers();
  });

  it('creates an authorization URL with PKCE and stores only opaque state in the cookie', () => {
    const jar = new MemoryCookies();
    const authorize = createEsignetLogin(cookiesForTest(jar), config());

    expect(authorize.origin + authorize.pathname).toBe('https://esignet-ui.example.test/authorize');
    expect(authorize.searchParams.get('response_type')).toBe('code');
    expect(authorize.searchParams.get('code_challenge_method')).toBe('S256');
    expect(authorize.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(jar.values.get(ESIGNET_LOGIN_COOKIE)).toBe(authorize.searchParams.get('state'));
    expect(jar.values.get(ESIGNET_LOGIN_COOKIE)).not.toMatch(
      new RegExp(String.raw`\b[2-9]\d{9}\b|NID` + String.raw`-\d+`)
    );
  });

  it('exchanges the code and derives the session from the configured UserInfo claim', async () => {
    const jar = new MemoryCookies();
    const cfg = config();
    const authorize = createEsignetLogin(cookiesForTest(jar), cfg);
    let tokenRequestBody = '';
    const fetchFn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      if (url === cfg.tokenEndpoint) {
        tokenRequestBody = init?.body?.toString() ?? '';
        return new Response(JSON.stringify({ access_token: 'test-access-token', token_type: 'Bearer' }), {
          headers: { 'content-type': 'application/json' }
        });
      }
      if (url === cfg.userinfoEndpoint) {
        expect(init?.headers).toMatchObject({ authorization: 'Bearer test-access-token' });
        return new Response(
          JSON.stringify({
            iss: cfg.issuer,
            sub: 'partner-specific-user-token',
            individual_id: '2300018263',
            name: 'Elena Dela Cruz'
          }),
          { headers: { 'content-type': 'application/json' } }
        );
      }
      return new Response('not found', { status: 404 });
    });

    const session = await completeEsignetLogin(cookiesForTest(jar), callbackUrl(authorize), cfg, fetchFn);
    const body = new URLSearchParams(tokenRequestBody);

    expect(body.get('grant_type')).toBe('authorization_code');
    expect(body.get('client_assertion_type')).toBe('urn:ietf:params:oauth:client-assertion-type:jwt-bearer');
    expect(body.get('client_assertion')?.split('.')).toHaveLength(3);
    expect(body.get('code_verifier')).toBeTruthy();
    expect(session).toEqual({ subject: '2300018263', displayName: 'Elena Dela Cruz' });
    expect(jar.values.has(ESIGNET_LOGIN_COOKIE)).toBe(false);
  });

  it('rejects UserInfo that omits the configured subject claim instead of falling back to sub', async () => {
    const jar = new MemoryCookies();
    const cfg = config();
    const authorize = createEsignetLogin(cookiesForTest(jar), cfg);
    const fetchFn = vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url === cfg.tokenEndpoint) {
        return new Response(JSON.stringify({ access_token: 'test-access-token' }), {
          headers: { 'content-type': 'application/json' }
        });
      }
      return new Response(JSON.stringify({ iss: cfg.issuer, sub: '2300018263', name: 'Elena Dela Cruz' }), {
        headers: { 'content-type': 'application/json' }
      });
    });

    await expect(completeEsignetLogin(cookiesForTest(jar), callbackUrl(authorize), cfg, fetchFn)).rejects.toThrow(
      'configured subject claim individual_id'
    );
  });

  it('keeps the eSignet client disabled unless PORTAL_AUTH_PROVIDER=esignet', () => {
    expect(esignetConfigFor(new URL('https://portal.example.test/auth/login'), {} as NodeJS.ProcessEnv)).toBeNull();
  });
});
