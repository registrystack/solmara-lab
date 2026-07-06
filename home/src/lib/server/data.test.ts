import { describe, expect, it } from 'vitest';
import { readComposeServices, readPurposes, readStatus, readVersions } from './data';

describe('home data adapters', () => {
  it('parses the purpose register from the normative docs page', async () => {
    const purposes = await readPurposes();
    expect(purposes).toHaveLength(6);
    expect(purposes[0].iri).toBe('https://id.registrystack.org/solmara/purpose/child-benefit-review');
    expect(purposes[0].denialCodes).toContain('pdp.purpose_not_permitted');
  });

  it('derives anatomy services from compose', async () => {
    const services = await readComposeServices();
    expect(services).toContain('scenario-runner');
    expect(services).toContain('portal');
    expect(services).toContain('static-metadata');
  });

  it('reads pinned versions for the trust strip', async () => {
    const versions = await readVersions();
    expect(versions.REGISTRY_RELAY_IMAGE).toMatch(/@sha256:/);
    expect(versions.REGISTRY_NOTARY_IMAGE).toMatch(/@sha256:/);
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
