import { describe, expect, it } from 'vitest';
import { SECURITY_HEADERS } from './hooks.server';

describe('security headers', () => {
  it('sets the required visitor center posture', () => {
    expect(SECURITY_HEADERS['X-Frame-Options']).toBe('DENY');
    expect(SECURITY_HEADERS['Referrer-Policy']).toBe('no-referrer');
    expect(SECURITY_HEADERS['X-Content-Type-Options']).toBe('nosniff');
    expect(SECURITY_HEADERS['Permissions-Policy']).toBe('camera=(), microphone=(), geolocation=()');
  });

  it('leaves Content-Security-Policy to SvelteKit kit.csp so the hydration script keeps its nonce', () => {
    expect(SECURITY_HEADERS).not.toHaveProperty('Content-Security-Policy');
  });
});
