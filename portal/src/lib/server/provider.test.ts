import { afterEach, describe, expect, it } from 'vitest';
import { env } from '$env/dynamic/private';
import { MockEvidenceProvider } from '$lib/providers/mock';
import { getProvider, resetProviderForTests } from './provider';

describe('getProvider', () => {
  afterEach(() => {
    resetProviderForTests();
    for (const key of Object.keys(env)) {
      delete env[key];
    }
  });

  it('keeps mock mode available by default', () => {
    expect(getProvider()).toBeInstanceOf(MockEvidenceProvider);
  });

  it('constructs live mode from environment config', () => {
    Object.assign(env, {
      PORTAL_PROVIDER: 'live',
      CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
      CRA_CITIZEN_CLIENT_TOKEN: 'cra-citizen-token',
      NIA_NOTARY_URL: 'https://nia-notary.solmara.registrystack.org',
      NIA_CITIZEN_CLIENT_TOKEN: 'nia-citizen-token'
    });

    expect(getProvider()).not.toBeInstanceOf(MockEvidenceProvider);
  });

  it('does not require obsolete Relay or generic Notary configuration', () => {
    Object.assign(env, {
      PORTAL_PROVIDER: 'live'
    });

    expect(() => getProvider()).not.toThrow();
  });

  it('does not silently fall back to mock for unknown modes', () => {
    env.PORTAL_PROVIDER = 'fixture';
    expect(() => getProvider()).toThrow('Unknown PORTAL_PROVIDER "fixture"');
  });
});
