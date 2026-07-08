import { describe, expect, it } from 'vitest';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { readSeedSummary, readSmokeEvidence } from './evidence';

describe('smoke evidence reader', () => {
  it('reports the newest smoke artifact with a BFF href', async () => {
    const labRoot = await fixtureLabRoot(async (root) => {
      await mkdir(path.join(root, 'output/smoke'), { recursive: true });
      await writeFile(path.join(root, 'output/smoke/story-previews.json'), '{}\n');
    });
    try {
      const evidence = await readSmokeEvidence(labRoot);
      expect(evidence.available).toBe(true);
      expect(evidence.file?.endsWith('.json')).toBe(true);
      expect(evidence.href).toBe('/api/smoke/latest');
      expect(evidence.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    } finally {
      await rm(labRoot, { force: true, recursive: true });
    }
  });
});

describe('seed summary reader', () => {
  it('summarises the generated seed from the generator output', async () => {
    const labRoot = await fixtureLabRoot(async (root) => {
      await mkdir(path.join(root, 'generator/output/shared'), { recursive: true });
      await writeFile(path.join(root, 'generator/output/checksums.sha256'), 'hash  one.csv\nhash  two.csv\n');
      await writeFile(path.join(root, 'generator/output/shared/personas.csv'), 'id,observed_at\n1,2026-01-02T00:00:00Z\n');
    });
    try {
      const seed = await readSeedSummary(labRoot);
      expect(seed.available).toBe(true);
      expect(seed.artifactCount).toBe(2);
      expect(seed.observedAt).toBe('2026-01-02');
    } finally {
      await rm(labRoot, { force: true, recursive: true });
    }
  });
});

async function fixtureLabRoot(seed: (root: string) => Promise<void>): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), 'solmara-home-evidence-'));
  await seed(root);
  return root;
}
