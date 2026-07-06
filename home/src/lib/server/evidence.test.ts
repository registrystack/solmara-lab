import { describe, expect, it } from 'vitest';
import { readSeedSummary, readSmokeEvidence } from './evidence';

describe('smoke evidence reader', () => {
  it('reports the newest smoke artifact with a BFF href', async () => {
    const evidence = await readSmokeEvidence();
    // The repo ships smoke artifacts under output/smoke, so this resolves.
    expect(evidence.available).toBe(true);
    expect(evidence.file?.endsWith('.json')).toBe(true);
    expect(evidence.href).toBe('/api/smoke/latest');
    expect(evidence.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });
});

describe('seed summary reader', () => {
  it('summarises the generated seed from the generator output', async () => {
    const seed = await readSeedSummary();
    expect(seed.available).toBe(true);
    expect(seed.artifactCount ?? 0).toBeGreaterThan(0);
    expect(seed.observedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
