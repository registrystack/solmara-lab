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

  it('publishes the exact Registry Stack release identity', async () => {
    const versions = await readVersions();
    expect(versions.REGISTRY_STACK_REQUIRED_VERSION).toBe('0.21.0');
    expect(versions.REGISTRY_STACK_SOURCE_REF).toBe('v0.21.0');
    expect(versions.REGISTRY_STACK_SOURCE_COMMIT).toMatch(/^[0-9a-f]{40}$/);
    expect(versions.REGISTRY_RELAY_IMAGE).toMatch(/@sha256:[0-9a-f]{64}$/);
    expect(versions.SOLMARA_EVIDENCE_IMAGE).toMatch(/^ghcr\.io\/registrystack\/evidence@sha256:[0-9a-f]{64}$/);
    expect(versions.SOLMARA_MINT_IMAGE).toMatch(/^ghcr\.io\/registrystack\/mint@sha256:[0-9a-f]{64}$/);
  });

  it('keeps compose-internal health probes out of visitor links', async () => {
    const status = await readStatus(async (url) => {
      return new Response('{}', { status: String(url).includes('/health') ? 200 : 503 });
    });
    const runner = status.find((item) => item.id === 'scenario-runner');
    const metadata = status.find((item) => item.id === 'deterministic-publisher');
    expect(runner?.status).toBe('up');
    expect(runner?.href).toBeUndefined();
    expect(metadata?.href).toBe('/.well-known/api-catalog');
  });
});
