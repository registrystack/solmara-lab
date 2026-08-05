import { describe, expect, it } from 'vitest';
import { statusProbes, topologyGroups } from './services';

describe('status probe table', () => {
  it('covers six Records APIs, Evidence, Mint, and shared applications', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    expect(probes.filter((probe) => probe.role === 'relay')).toHaveLength(6);
    expect(probes.filter((probe) => probe.role === 'evidence')).toHaveLength(2);
    expect(probes.filter((probe) => probe.role === 'shared').length).toBeGreaterThanOrEqual(4);
  });

  it('uses public health probes for Evidence and Mint', () => {
    const probes = statusProbes('http://127.0.0.1:4300');
    expect(probes.find((probe) => probe.id === 'registry-evidence')?.probeUrl).toBe(
      'https://localhost:4341/health'
    );
    expect(probes.find((probe) => probe.id === 'registry-mint')?.probeUrl).toBe(
      'https://localhost:4341/health'
    );
    expect(probes.find((probe) => probe.id === 'cra-civil-relay')?.probeUrl?.endsWith('/')).toBe(true);
  });

  it('reads compose-internal Evidence and Mint origins from the environment', () => {
    const probes = statusProbes('http://127.0.0.1:4300', {
      EVIDENCE_URL: 'http://evidence:8080',
      MINT_URL: 'http://mint:8081'
    });
    expect(probes.find((probe) => probe.id === 'registry-evidence')?.probeUrl).toBe('http://evidence:8080/health');
    expect(probes.find((probe) => probe.id === 'registry-mint')?.probeUrl).toBe('http://mint:8081/health');
  });

  it('only marks browser-facing services with open links', () => {
    const probes = statusProbes('http://portal.example');
    expect(probes.find((probe) => probe.id === 'metadata')?.href).toBe('/.well-known/api-catalog');
    expect(probes.find((probe) => probe.id === 'portal')?.href).toBe('http://portal.example');
    expect(probes.find((probe) => probe.id === 'home')?.href).toBe('/');
    expect(probes.find((probe) => probe.id === 'registry-evidence')?.href).toBeUndefined();
  });
});

describe('topology groups', () => {
  const groups = topologyGroups('https://github.com/registrystack/solmara-lab');

  it('groups authority Records APIs, Evidence and Mint, and shared services', () => {
    expect(groups.map((group) => group.key)).toEqual(['relays', 'evidence', 'shared']);
    expect(groups[0].services).toHaveLength(6);
    expect(groups[1].services.map((service) => service.id)).toEqual(['registry-evidence', 'registry-mint']);
  });

  it('links Evidence to its runtime and reviewed bundle', () => {
    const evidence = groups[1].services.find((service) => service.id === 'registry-evidence');
    expect(evidence?.config.map((link) => link.path)).toEqual(['evidence/runtime.yaml', 'evidence/bundle']);
    expect(evidence?.config[1].url).toBe('https://github.com/registrystack/solmara-lab/tree/main/evidence/bundle');
  });
});
