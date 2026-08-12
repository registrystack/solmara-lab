import { describe, expect, it } from 'vitest';
import { statusProbes, topologyGroups } from './services';

describe('authority-cell topology', () => {
  it('has exactly five Relays, six Evidence cells, and one shared Mint', () => {
    const probes = statusProbes('http://portal.example');
    expect(probes.filter((probe) => probe.role === 'relay')).toHaveLength(5);
    expect(probes.filter((probe) => probe.role === 'evidence')).toHaveLength(6);
    expect(probes.filter((probe) => probe.id === 'lab-mint')).toHaveLength(1);
    expect(probes.filter((probe) => probe.id === 'mosd-relay')).toHaveLength(1);
    expect(probes.some((probe) => probe.id === 'sro-relay')).toBe(false);
    expect(probes.some((probe) => probe.id === 'registry-evidence')).toBe(false);
  });

  it('uses distinct authority Evidence identities and configurable origins', () => {
    const probes = statusProbes('http://portal.example', {
      SOLMARA_CRA_EVIDENCE_URL: 'https://cra.example',
      SOLMARA_NIA_EVIDENCE_URL: 'https://nia.example'
    });
    expect(probes.find((probe) => probe.id === 'cra-evidence')?.probeUrl).toBe('https://cra.example/health');
    expect(probes.find((probe) => probe.id === 'nia-evidence')?.probeUrl).toBe('https://nia.example/health');
  });

  it('links only browser-facing services', () => {
    const probes = statusProbes('http://portal.example');
    expect(probes.find((probe) => probe.id === 'deterministic-publisher')?.href).toBe('/.well-known/api-catalog');
    expect(probes.find((probe) => probe.id === 'portal')?.href).toBe('http://portal.example');
    expect(probes.find((probe) => probe.id === 'cra-evidence')?.href).toBeUndefined();
  });

  it('renders the approved deterministic topology groups and owned configs', () => {
    const groups = topologyGroups('https://github.com/registrystack/solmara-lab');
    expect(groups.map((group) => group.key)).toEqual(['publisher', 'relays', 'evidence', 'programme', 'identity']);
    expect(groups.find((group) => group.key === 'relays')?.services).toHaveLength(5);
    expect(groups.find((group) => group.key === 'evidence')?.services.filter((service) => service.role === 'evidence')).toHaveLength(6);
    expect(groups.find((group) => group.key === 'evidence')?.services.find((service) => service.id === 'cra-evidence')?.config[0].path).toBe('evidence/cells/cra');
    expect(groups.find((group) => group.key === 'identity')?.services[0].blurb).toContain('NIA Relay');
  });
});
