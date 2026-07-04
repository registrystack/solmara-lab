import { env } from '$env/dynamic/private';
import type { DetailedEvidenceProvider } from '$lib/providers/EvidenceProvider';
import { LiveEvidenceProvider, type LiveProviderEnv } from '$lib/providers/live';
import { MockEvidenceProvider } from '$lib/providers/mock';

// Memoized: a single instance per process keeps the trace sequence monotonic across
// requests (a fresh instance per call would reset the event counter).
let cached: DetailedEvidenceProvider | undefined;
let cachedMode: string | undefined;

export function getProvider(): DetailedEvidenceProvider {
  const mode = env.PORTAL_PROVIDER ?? 'mock';
  if (cached && cachedMode === mode) return cached;
  if (mode !== 'mock') {
    if (mode !== 'live') {
      throw new Error(`Unknown PORTAL_PROVIDER "${mode}". Expected "mock" or "live".`);
    }
    cached = new LiveEvidenceProvider(env as LiveProviderEnv);
    cachedMode = mode;
    return cached;
  }
  cached = new MockEvidenceProvider();
  cachedMode = mode;
  return cached;
}

export function resetProviderForTests(): void {
  cached = undefined;
  cachedMode = undefined;
}
