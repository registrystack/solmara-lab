import { describe, expect, it } from 'vitest';
import { statusProbes, topologyGroups } from './services';

describe('status probe table', () => {
  it('covers the whole topology: shared services and six authority pairs', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    const relays = probes.filter((probe) => probe.role === 'relay');
    const notaries = probes.filter((probe) => probe.role === 'notary');
    const shared = probes.filter((probe) => probe.role === 'shared');
    expect(relays).toHaveLength(6);
    expect(notaries).toHaveLength(6);
    expect(shared.length).toBeGreaterThanOrEqual(4);
    expect(probes.length).toBeGreaterThanOrEqual(16);
  });

  it('probes the federator on health, notaries on claims, and relays on their gated root', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    const federator = probes.find((probe) => probe.id === 'child-benefit-federator');
    const notary = probes.find((probe) => probe.id === 'cra-notary');
    const relay = probes.find((probe) => probe.id === 'cra-civil-relay');
    expect(federator?.probeUrl).toContain('/health');
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
      CHILD_BENEFIT_FEDERATOR_URL: 'http://child-benefit-federator:8080'
    });
    expect(probes.find((probe) => probe.id === 'child-benefit-federator')?.probeUrl).toBe(
      'http://child-benefit-federator:8080/health'
    );
    // A service with no override keeps its localhost default.
    expect(probes.find((probe) => probe.id === 'sipf-notary')?.probeUrl).toBe('http://127.0.0.1:4322/v1/claims');
  });

  it('maps every Compose authority Notary environment name to exactly one probe', () => {
    const authorityOrigins = {
      CRA_NOTARY_URL: 'http://cra-notary:8081',
      NIA_NOTARY_URL: 'http://nia-notary:8081',
      SRO_NOTARY_URL: 'http://sro-notary:8081',
      PROGRAMME_NOTARY_URL: 'http://programme-notary:8081',
      SIPF_NOTARY_URL: 'http://sipf-notary:8081',
      NAGDI_NOTARY_URL: 'http://nagdi-notary:8081'
    };
    const probes = statusProbes('http://127.0.0.1:4300', authorityOrigins).filter(
      (probe) => probe.role === 'notary'
    );

    expect(Object.fromEntries(probes.map((probe) => [probe.id, probe.probeUrl]))).toEqual({
      'cra-notary': 'http://cra-notary:8081/v1/claims',
      'nia-notary': 'http://nia-notary:8081/v1/claims',
      'sro-notary': 'http://sro-notary:8081/v1/claims',
      'programme-notary': 'http://programme-notary:8081/v1/claims',
      'sipf-notary': 'http://sipf-notary:8081/v1/claims',
      'nagdi-notary': 'http://nagdi-notary:8081/v1/claims'
    });
  });

  it('marks home as self so it is reported up without a network probe', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    expect(probes.find((probe) => probe.id === 'home')?.self).toBe(true);
  });
});

describe('topology groups', () => {
  const groups = topologyGroups('https://github.com/registrystack/solmara-lab');

  it('groups six authority-owned Relays, six authority-owned Notaries, and shared services', () => {
    const keys = groups.map((group) => group.key);
    expect(keys).toEqual(['relays', 'notaries', 'shared']);
    expect(groups[0].services).toHaveLength(6);
    expect(groups[1].services).toHaveLength(6);
    expect(groups[1].services.every((service) => Boolean(service.authority))).toBe(true);
  });

  it('links every authority to its authored project and generated Relay config', () => {
    const cra = groups[0].services.find((service) => service.id === 'cra-civil-relay');
    expect(cra?.authority).toBe('Civil Registration Authority');
    const project = cra?.config.find((link) => link.label === 'Registry project');
    expect(project?.url).toBe(
      'https://github.com/registrystack/solmara-lab/blob/main/projects/cra-civil/registry-stack.yaml'
    );
    const generated = cra?.config.find((link) => link.label === 'Generated Relay config');
    expect(generated?.url).toBe(
      'https://github.com/registrystack/solmara-lab/blob/main/runtime/registry-projects/local/cra-civil/relay/relay.yaml'
    );
    const seed = cra?.config.find((link) => link.path === 'ministries/interior-civil');
    expect(seed?.url).toBe('https://github.com/registrystack/solmara-lab/tree/main/ministries/interior-civil');
  });

  it('links authority Notaries to their generated project closure', () => {
    const nia = groups[1].services.find((service) => service.id === 'nia-notary');
    expect(nia?.config).toEqual([
      {
        label: 'Generated Notary config',
        path: 'runtime/registry-projects/local/nia-population/notary/notary.yaml',
        url: 'https://github.com/registrystack/solmara-lab/blob/main/runtime/registry-projects/local/nia-population/notary/notary.yaml'
      }
    ]);
  });
});
