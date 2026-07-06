import { readFile, readdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { runtime } from './runtime';
import type { SeedSummary, SmokeEvidence } from '$lib/types';

const SMOKE_DIR = 'output/smoke';

/**
 * Find the newest smoke-evidence artifact under `output/smoke` and report its
 * timestamp honestly. When the directory is absent or empty the trust strip says
 * "no smoke evidence yet" rather than inventing a number. The `href` points at
 * the BFF route that serves the artifact so the browser never reads the
 * filesystem directly.
 */
export async function readSmokeEvidence(): Promise<SmokeEvidence> {
  const dir = path.join(runtime.labRoot, SMOKE_DIR);
  let entries: string[];
  try {
    entries = (await readdir(dir)).filter((name) => name.endsWith('.json'));
  } catch {
    return { available: false };
  }
  if (entries.length === 0) return { available: false };

  let newest: { name: string; mtimeMs: number } | null = null;
  for (const name of entries) {
    try {
      const info = await stat(path.join(dir, name));
      if (!newest || info.mtimeMs > newest.mtimeMs) newest = { name, mtimeMs: info.mtimeMs };
    } catch {
      // A file that vanished between readdir and stat is simply skipped.
    }
  }
  if (!newest) return { available: false };
  return {
    available: true,
    file: newest.name,
    timestamp: new Date(newest.mtimeMs).toISOString(),
    href: '/api/smoke/latest'
  };
}

/**
 * Summarise the generated data seed from the generator output rather than a
 * hardcoded string: the checksum manifest gives the artifact count and the
 * persona roster carries the observation date the generator stamped.
 */
export async function readSeedSummary(): Promise<SeedSummary> {
  const artifactCount = await readArtifactCount();
  const observedAt = await readObservedAt();
  if (artifactCount === null && !observedAt) return { available: false };
  return {
    available: true,
    ...(artifactCount === null ? {} : { artifactCount }),
    ...(observedAt ? { observedAt } : {})
  };
}

async function readArtifactCount(): Promise<number | null> {
  try {
    const raw = await readFile(path.join(runtime.labRoot, 'generator/output/checksums.sha256'), 'utf-8');
    const count = raw.split('\n').filter((line) => line.trim().length > 0).length;
    return count > 0 ? count : null;
  } catch {
    return null;
  }
}

async function readObservedAt(): Promise<string | null> {
  try {
    const raw = await readFile(path.join(runtime.labRoot, 'generator/output/shared/personas.csv'), 'utf-8');
    const [header, firstRow] = raw.split('\n');
    if (!header || !firstRow) return null;
    const columns = header.split(',');
    const index = columns.indexOf('observed_at');
    if (index === -1) return null;
    const value = firstRow.split(',')[index]?.trim();
    return value ? value.slice(0, 10) : null;
  } catch {
    return null;
  }
}
