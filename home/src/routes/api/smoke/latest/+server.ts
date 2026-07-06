import { error } from '@sveltejs/kit';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { runtime } from '$lib/server/runtime';
import { readSmokeEvidence } from '$lib/server/evidence';
import type { RequestHandler } from './$types';

/**
 * Serve the newest smoke-evidence artifact. The browser only talks to this home
 * route; it never reads the filesystem. The filename comes from
 * `readSmokeEvidence`, so only a `.json` file inside `output/smoke` can be
 * served (no path traversal from a client-supplied name).
 */
export const GET: RequestHandler = async () => {
  const evidence = await readSmokeEvidence();
  if (!evidence.available || !evidence.file) {
    throw error(404, 'no smoke evidence yet');
  }
  const body = await readFile(path.join(runtime.labRoot, 'output/smoke', evidence.file), 'utf-8');
  return new Response(body, {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Smoke-Artifact': evidence.file
    }
  });
};
