import { describe, expect, it } from 'vitest';
import { statusProbes, topologyGroups } from './services';

describe('status probe table', () => {
  it('covers the whole topology: shared services, six relays, four notaries', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    const relays = probes.filter((probe) => probe.role === 'relay');
    const notaries = probes.filter((probe) => probe.role === 'notary');
    const shared = probes.filter((probe) => probe.role === 'shared');
    expect(relays).toHaveLength(6);
    expect(notaries).toHaveLength(4);
    expect(shared.length).toBeGreaterThanOrEqual(3);
    expect(probes.length).toBeGreaterThanOrEqual(13);
  });

  it('probes notaries on an auth-gated data path and relays on their gated root', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    const notary = probes.find((probe) => probe.id === 'child-benefit-notary');
    const relay = probes.find((probe) => probe.id === 'cra-civil-relay');
    expect(notary?.probeUrl).toContain('/v1/claims');
    expect(relay?.probeUrl?.endsWith('/')).toBe(true);
  });

  it('only marks the browsable services with an open link', () => {
    const probes = statusProbes('http://portal.example');
    expect(probes.find((probe) => probe.id === 'metadata')?.href).toBe('/.well-known/api-catalog');
    expect(probes.find((probe) => probe.id === 'portal')?.href).toBe('http://portal.example');
    expect(probes.find((probe) => probe.id === 'home')?.href).toBe('/');
    expect(probes.find((probe) => probe.id === 'cra-civil-relay')?.href).toBeUndefined();
  });

  it('reads probe origins from the env table, overriding the localhost defaults', () => {
    const probes = statusProbes('http://127.0.0.1:4300', {
      CHILD_BENEFIT_NOTARY_URL: 'http://child-benefit-notary:8080'
    });
    expect(probes.find((probe) => probe.id === 'child-benefit-notary')?.probeUrl).toBe(
      'http://child-benefit-notary:8080/v1/claims'
    );
    // A service with no override keeps its localhost default.
    expect(probes.find((probe) => probe.id === 'pension-notary')?.probeUrl).toBe('http://127.0.0.1:4322/v1/claims');
  });

  it('marks home as self so it is reported up without a network probe', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    expect(probes.find((probe) => probe.id === 'home')?.self).toBe(true);
  });
});

describe('topology groups', () => {
  const groups = topologyGroups('https://github.com/registrystack/solmara-lab');

  it('groups relays by authority, notaries by purpose, and the shared services', () => {
    const keys = groups.map((group) => group.key);
    expect(keys).toEqual(['relays', 'notaries', 'shared']);
    expect(groups[0].services).toHaveLength(6);
    expect(groups[1].services).toHaveLength(4);
  });

  it('links every ministry config to the repo with the in-repo path preserved', () => {
    const cra = groups[0].services.find((service) => service.id === 'cra-civil-relay');
    expect(cra?.authority).toBe('Civil Registration Authority');
    const manifest = cra?.config.find((link) => link.path.endsWith('relay.yaml'));
    expect(manifest?.url).toBe(
      'https://github.com/registrystack/solmara-lab/blob/main/ministries/interior-civil/config/relay.yaml'
    );
    const seed = cra?.config.find((link) => link.path === 'ministries/interior-civil');
    expect(seed?.url).toBe('https://github.com/registrystack/solmara-lab/tree/main/ministries/interior-civil');
  });
});
