import type { RequestSource } from '$lib/types';

/**
 * Select the HTTP requests that a visitor can actually run. Multi-authority
 * stories use a synthetic primary request to describe orchestration, while
 * request_sources carries the underlying authority calls.
 */
export function runnableRequestSources(
  primary: RequestSource,
  sources: RequestSource[] | undefined
): RequestSource[] {
  return sources?.length ? sources : [primary];
}

/**
 * Render a request as a copy-as-curl snippet. Headers are prepared server-side:
 * redacted by default, with only allowlisted synthetic lab tokens republished
 * for the visitor center. URLs are already rewritten to host-reachable ones.
 */
export function toCurl(source: RequestSource | undefined, overrideHeaders: Record<string, string> = {}): string {
  if (!source || !source.url) return '';
  const method = (source.method ?? 'GET').toUpperCase();
  const headers = { ...(source.headers ?? {}), ...overrideHeaders };
  const lines: string[] = [`curl -sS -X ${method} '${source.url}'`];
  for (const [key, value] of Object.entries(headers)) {
    lines.push(`  -H '${key}: ${value}'`);
  }
  if (source.body !== undefined && source.body !== null) {
    const body = typeof source.body === 'string' ? source.body : JSON.stringify(source.body);
    lines.push(`  -d '${body.replace(/'/g, "'\\''")}'`);
  }
  return lines.join(' \\\n');
}
