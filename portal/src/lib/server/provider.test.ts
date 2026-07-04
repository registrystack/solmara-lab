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
      PORTAL_CITIZEN_NOTARY_URL: 'https://citizen-notary.lab.registrystack.org',
      PORTAL_CITIZEN_NOTARY_TOKEN: 'notary-token',
      PORTAL_RELAY_TOKEN: 'relay-token',
      PORTAL_RELAY_URLS: JSON.stringify({
        civil: 'https://civil-relay.lab.registrystack.org',
        social: 'https://social-relay.lab.registrystack.org',
        agri: 'https://nagdi-relay.lab.registrystack.org',
        certs: 'https://civil-relay.lab.registrystack.org'
      })
    });

    expect(getProvider()).not.toBeInstanceOf(MockEvidenceProvider);
  });

  it('requires a Relay token in live mode', () => {
    Object.assign(env, {
      PORTAL_PROVIDER: 'live',
      PORTAL_CITIZEN_NOTARY_URL: 'https://citizen-notary.lab.registrystack.org',
      PORTAL_CITIZEN_NOTARY_TOKEN: 'notary-token',
      PORTAL_RELAY_URLS: JSON.stringify({
        civil: 'https://civil-relay.lab.registrystack.org',
        social: 'https://social-relay.lab.registrystack.org',
        agri: 'https://nagdi-relay.lab.registrystack.org',
        certs: 'https://civil-relay.lab.registrystack.org'
      })
    });

    expect(() => getProvider()).toThrow('PORTAL_RELAY_TOKEN is required');
  });

  it('does not silently fall back to mock for unknown modes', () => {
    env.PORTAL_PROVIDER = 'fixture';
    expect(() => getProvider()).toThrow('Unknown PORTAL_PROVIDER "fixture"');
  });
});
