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
 * Render an already-safe request as a copy-as-curl snippet. Runtime credential
 * markers are omitted rather than copied into the browser.
 */
export function toCurl(source: RequestSource | undefined, overrideHeaders: Record<string, string> = {}): string {
  if (!source || !source.url) return '';
  const method = (source.method ?? 'GET').toUpperCase();
  const headers = { ...(source.headers ?? {}), ...overrideHeaders };
  const lines: string[] = [`curl -sS -X ${method} '${source.url}'`];
  for (const [key, value] of Object.entries(headers)) {
    if (/authorization|x-api-key/i.test(key) || /runtime token hidden|bearer\s+[a-z0-9._-]+/i.test(value)) continue;
    lines.push(`  -H '${key}: ${value}'`);
  }
  if (source.body !== undefined && source.body !== null) {
    const body = typeof source.body === 'string' ? source.body : JSON.stringify(source.body);
    lines.push(`  -d '${body.replace(/'/g, "'\\''")}'`);
  }
  return lines.join(' \\\n');
}
