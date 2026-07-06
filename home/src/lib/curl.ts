import type { RequestSource } from '$lib/types';

/**
 * Render a request as a copy-as-curl snippet. Headers are already redacted by
 * the scenario runner, and URLs are already rewritten to host-reachable ones
 * server-side, so this is a pure presentation helper safe to run in the browser.
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
