import { env } from '$env/dynamic/private';
import path from 'node:path';

export const runtime = {
  labRoot: env.SOLMARA_LAB_ROOT ?? path.resolve(process.cwd(), '..'),
  portalUrl: trimSlash(env.PORTAL_URL ?? 'http://127.0.0.1:4300'),
  scenarioRunnerUrl: trimSlash(env.SCENARIO_RUNNER_URL ?? 'http://127.0.0.1:4302'),
  staticMetadataUrl: trimSlash(env.STATIC_METADATA_URL ?? 'http://127.0.0.1:4331'),
  repoUrl: trimSlash(env.REPO_URL ?? 'https://github.com/registrystack/solmara-lab')
};

export function joinedUrl(base: string, path: string): string {
  return `${trimSlash(base)}/${path.replace(/^\//, '')}`;
}

export function trimSlash(value: string): string {
  return value.replace(/\/$/, '');
}
