import { describe, expect, it } from 'vitest';
import { readComposeServices, readPurposes, readStatus, readVersions } from './data';

describe('home data adapters', () => {
  it('parses the purpose register from the normative docs page', async () => {
    const purposes = await readPurposes();
    expect(purposes).toHaveLength(6);
    expect(purposes[0].iri).toBe('child-benefit-review');
    expect(purposes[0].denialCodes).toContain('not_authorized');
  });

  it('derives anatomy services from compose', async () => {
    const services = await readComposeServices();
    expect(services).toContain('scenario-runner');
    expect(services).toContain('portal');
    expect(services).toContain('static-metadata');
  });

  it('reads the exact release tag, source commit, and local Evidence image names', async () => {
    const versions = await readVersions();
    expect(versions.REGISTRY_STACK_SOURCE_REF).toBe('v0.18.0');
    expect(versions.REGISTRY_STACK_SOURCE_COMMIT).toMatch(/^[0-9a-f]{40}$/);
    expect(versions.SOLMARA_EVIDENCE_IMAGE).toBe('solmara-lab-registry-evidence:v0.18.0');
    expect(versions.SOLMARA_MINT_IMAGE).toBe('solmara-lab-registry-mint:v0.18.0');
  });

  it('keeps compose-internal health probes out of visitor links', async () => {
    const status = await readStatus(async (url) => {
      return new Response('{}', { status: String(url).includes('/health') ? 200 : 503 });
    });
    const runner = status.find((item) => item.id === 'scenario-runner');
    const metadata = status.find((item) => item.id === 'metadata');
    expect(runner?.status).toBe('up');
    expect(runner?.href).toBeUndefined();
    expect(metadata?.href).toBe('/.well-known/api-catalog');
  });
});
