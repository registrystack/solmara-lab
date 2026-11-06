import { beforeEach, describe, expect, it } from 'vitest';
import type { Cookies } from '@sveltejs/kit';
import { getSession, resetMockSessions, SESSION_COOKIE } from '$lib/server/session';
import { GET as login } from './login/+server';
import { GET as callback } from './callback/+server';

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

// The handlers redirect by throwing; capture the redirect status and location.
async function redirectOf(run: () => unknown): Promise<{ status: number; location: string }> {
  try {
    await run();
  } catch (thrown) {
    const redirect = thrown as { status?: number; location?: string };
    if (redirect.status !== undefined && redirect.location !== undefined) {
      return { status: redirect.status, location: redirect.location };
    }
    throw thrown;
  }
  throw new Error('handler did not redirect');
}

function callbackEvent(jar: MemoryCookies, search = '') {
  // Test double implements only the pieces of the event these handlers read.
  return { cookies: jar as unknown as Cookies, url: new URL(`http://portal.test/auth/callback${search}`) };
}

describe('mock login routes', () => {
  beforeEach(() => resetMockSessions());

  it('login redirects to the callback', async () => {
    const event = { url: new URL('http://portal.test/auth/login') };
    const result = await redirectOf(() => login(event as never));
    expect(result).toEqual({ status: 302, location: '/auth/callback' });
  });

  it('login carries a persona hint through to the callback', async () => {
    const event = { url: new URL('http://portal.test/auth/login?persona=2300010248') };
    const result = await redirectOf(() => login(event as never));
    expect(result.location).toBe('/auth/callback?persona=2300010248');
  });

  it('callback binds the default session without a hint', async () => {
    const jar = new MemoryCookies();
    const result = await redirectOf(() => callback(callbackEvent(jar) as never));
    expect(result).toEqual({ status: 302, location: '/services' });
    expect(getSession(jar as unknown as Cookies)?.displayName).toBe('Elena Dela Cruz');
    expect(jar.get(SESSION_COOKIE)).toBeTruthy();
  });

  it('callback binds a rostered persona', async () => {
    const jar = new MemoryCookies();
    await redirectOf(() => callback(callbackEvent(jar, '?persona=2300010248') as never));
    expect(getSession(jar as unknown as Cookies)).toEqual({
      subject: '2300010248',
      displayName: 'Mateo Santos'
    });
  });

  it('callback ignores a persona off the roster and ignores OIDC parameters', async () => {
    const jar = new MemoryCookies();
    await redirectOf(() =>
      callback(callbackEvent(jar, '?persona=9999999999&code=abc&state=xyz') as never)
    );
    expect(getSession(jar as unknown as Cookies)?.subject).toBe('2300018263');
  });
});
