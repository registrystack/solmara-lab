import { env } from '$env/dynamic/private';

/**
 * The scenario runner reports compose-internal service URLs (for example
 * `http://child-benefit-federator:8080/...`) because that is what it actually
 * calls inside the compose network. None of those hostnames resolve from a
 * visitor's browser, so every user-facing URL and copy-as-curl snippet is
 * rewritten through this single table before it leaves the server.
 *
 * The table is keyed by the internal `host:port` origin and mirrors the
 * conventions in `scenarios/service_config.py` and the compose port mappings.
 * Local development maps onto the published localhost ports; the hosted deploy
 * overrides the table with `SOLMARA_PUBLIC_URL_MAP` so the same code emits
 * `*.solmara.registrystack.org` URLs.
 */
const DEFAULT_LOCAL_MAP: Record<string, string> = {
  'child-benefit-federator:8080': 'http://localhost:4321',
  'cra-notary:8081': 'http://localhost:4325',
  'nia-notary:8081': 'http://localhost:4326',
  'sro-notary:8081': 'http://localhost:4327',
  'programme-notary:8081': 'http://localhost:4328',
  'sipf-notary:8081': 'http://localhost:4322',
  'nagdi-notary:8081': 'http://localhost:4323',
  'cra-civil-relay:8080': 'http://localhost:4311',
  'nia-population-relay:8080': 'http://localhost:4312',
  'sro-social-relay:8080': 'http://localhost:4313',
  'programme-mis-relay:8080': 'http://localhost:4314',
  'sipf-pensions-relay:8080': 'http://localhost:4315',
  'nagdi-agriculture-relay:8080': 'http://localhost:4316',
  'static-metadata:8080': 'http://localhost:4331',
  'scenario-runner:8080': 'http://localhost:4302',
  'portal:4000': 'http://localhost:4300'
};

export type PublicUrlMap = Record<string, string>;

/**
 * Build the public URL map from the baked-in local defaults plus an optional
 * JSON override (defaults to the `SOLMARA_PUBLIC_URL_MAP` environment
 * variable). The override is a JSON object of `internalHost:port -> publicOrigin`.
 */
export function buildPublicUrlMap(overrideJson: string | undefined = env.SOLMARA_PUBLIC_URL_MAP): PublicUrlMap {
  const map: PublicUrlMap = { ...DEFAULT_LOCAL_MAP };
  if (!overrideJson) return map;
  try {
    const parsed = JSON.parse(overrideJson) as unknown;
    if (parsed && typeof parsed === 'object') {
      for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof value === 'string' && value) map[key] = trimSlash(value);
      }
    }
  } catch {
    // A malformed override must not take the page down; fall back to defaults.
  }
  return map;
}

/**
 * Rewrite the origin of a single URL through the map. Path and query are kept.
 * Non-URL strings and origins that are not in the table are returned unchanged,
 * so already host-reachable URLs pass straight through.
 */
export function mapPublicUrl(value: string, map: PublicUrlMap): string {
  if (!value) return value;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return value;
  }
  const publicOrigin = map[parsed.host];
  if (!publicOrigin) return value;
  return `${trimSlash(publicOrigin)}${parsed.pathname}${parsed.search}`;
}

/**
 * Return a copy of a scenario run result with the internal URLs in its
 * request blocks and ordinary source trace rewritten to host-reachable URLs.
 * The input is not mutated.
 */
export function rewriteRequestUrls<T extends Record<string, unknown>>(result: T, map: PublicUrlMap): T {
  const clone: Record<string, unknown> = { ...result };
  for (const key of ['request_source', 'credential_source']) {
    const source = clone[key];
    if (source && typeof source === 'object' && typeof (source as { url?: unknown }).url === 'string') {
      clone[key] = { ...(source as object), url: mapPublicUrl((source as { url: string }).url, map) };
    }
  }
  if (Array.isArray(clone.request_sources)) {
    clone.request_sources = clone.request_sources.map((source) => rewriteSourceUrl(source, map));
  }
  if (Array.isArray(clone.source_trace)) {
    clone.source_trace = clone.source_trace.map((item) => {
      if (!item || typeof item !== 'object') return item;
      const trace = { ...(item as Record<string, unknown>) };
      trace.request_source = rewriteSourceUrl(trace.request_source, map);
      trace.request_summary = rewriteSourceUrl(trace.request_summary, map);
      return trace;
    });
  }
  return clone as T;
}

function rewriteSourceUrl(source: unknown, map: PublicUrlMap): unknown {
  if (!source || typeof source !== 'object' || typeof (source as { url?: unknown }).url !== 'string') return source;
  return { ...(source as object), url: mapPublicUrl((source as { url: string }).url, map) };
}

function trimSlash(value: string): string {
  return value.replace(/\/$/, '');
}
