import { env } from '$env/dynamic/private';
import { buildPublicUrlMap, mapPublicUrl } from './urlmap';
import type { CurlExample, PublishedToken } from '$lib/types';

const CHILD_PURPOSE = 'https://id.registrystack.org/solmara/purpose/child-benefit-review';
const PENSION_PURPOSE = 'https://id.registrystack.org/solmara/purpose/pension-payment-review';
const SURVIVOR_PURPOSE = 'https://id.registrystack.org/solmara/purpose/survivor-benefit-determination';
const VOUCHER_PURPOSE = 'https://id.registrystack.org/solmara/purpose/voucher-eligibility-review';
const LIVESTOCK_PURPOSE = 'https://id.registrystack.org/solmara/purpose/livestock-movement-control';
const CITIZEN_PURPOSE = 'https://id.registrystack.org/solmara/purpose/citizen-self-service';

const TOKEN_URL_HINTS: Record<string, string[]> = {
  'child-benefit-federator': ['child-benefit-federator', 'localhost:4321', '127.0.0.1:4321'],
  'pension-notary': ['pension-notary', 'localhost:4322', '127.0.0.1:4322'],
  'nagdi-notary': ['nagdi-notary', 'localhost:4323', '127.0.0.1:4323'],
  'citizen-notary': ['citizen-notary', 'localhost:4324', '127.0.0.1:4324']
};

const TOKEN_PURPOSES: Record<string, string[]> = {
  'child-benefit-federator': [CHILD_PURPOSE],
  'pension-notary': [PENSION_PURPOSE, SURVIVOR_PURPOSE],
  'nagdi-notary': [VOUCHER_PURPOSE, LIVESTOCK_PURPOSE],
  'citizen-notary': [CITIZEN_PURPOSE]
};

/**
 * Notes and purposes for the names the lab deliberately publishes. Only names in
 * `HOME_PUBLISHED_TOKENS` are ever surfaced; this map only supplies copy.
 */
const TOKEN_NOTES: Record<string, { purpose: string; note: string }> = {
  'child-benefit-federator': {
    purpose: CHILD_PURPOSE,
    note: 'Scoped to the child benefit federator. Use it to collect source-owned predicates under child-benefit-review.'
  },
  'pension-notary': {
    purpose: PENSION_PURPOSE,
    note: 'Scoped to the pension notary for pension stop and survivor benefit review.'
  },
  'nagdi-notary': {
    purpose: VOUCHER_PURPOSE,
    note: 'Scoped to the NAgDI notary for farmer voucher and livestock movement review.'
  },
  'citizen-notary': {
    purpose: CITIZEN_PURPOSE,
    note: 'Scoped to the citizen notary that backs the portal preview evidence.'
  }
};

/**
 * Parse the server-side published-token allowlist. This is the ONLY source of
 * tokens the page ever renders: a token that is not a value in
 * `HOME_PUBLISHED_TOKENS` can never reach page data, no matter what other token
 * environment variables the container holds. A malformed allowlist yields an
 * empty list rather than falling back to any other env.
 */
export function parsePublishedTokens(json: string | undefined = env.HOME_PUBLISHED_TOKENS): PublishedToken[] {
  if (!json) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return [];
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return [];
  const tokens: PublishedToken[] = [];
  for (const [name, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (typeof value !== 'string' || value.length === 0) continue;
    const meta = TOKEN_NOTES[name];
    tokens.push({
      name,
      token: value,
      purpose: meta?.purpose,
      note: meta?.note ?? 'Synthetic lab token, safe to publish. Scoped to one notary.'
    });
  }
  return tokens;
}

/**
 * Story run results arrive from the scenario runner with runtime auth redacted.
 * The visitor center may republish only the synthetic lab tokens listed in
 * HOME_PUBLISHED_TOKENS so story-level copy-as-curl snippets are reproducible.
 */
export function publishRequestTokens<T extends Record<string, unknown>>(result: T, tokens: PublishedToken[]): T {
  const published = new Map(tokens.map((token) => [token.name, token.token]));
  const clone: Record<string, unknown> = { ...result };
  for (const key of ['request_source', 'credential_source']) {
    clone[key] = publishRequestSourceToken(clone[key], published);
  }
  return clone as T;
}

function publishRequestSourceToken(source: unknown, published: Map<string, string>): unknown {
  if (!isObject(source)) return source;
  const headers = isObject(source.headers) ? stringHeaders(source.headers) : {};
  const token = tokenCandidates(source.url, headers['Data-Purpose'])
    .map((name) => published.get(name))
    .find((value): value is string => typeof value === 'string');
  if (!token) return source;

  const apiKeyHeader = Object.keys(headers).find((key) => key.toLowerCase() === 'x-api-key');
  if (!apiKeyHeader) return source;
  return {
    ...source,
    headers: {
      ...headers,
      [apiKeyHeader]: token
    }
  };
}

function tokenCandidates(url: unknown, purpose: string | undefined): string[] {
  const names = [tokenNameForUrl(url), tokenNameForPurpose(purpose)].filter((name): name is string => Boolean(name));
  if (purpose === CHILD_PURPOSE) names.push('child-benefit-federator');
  return [...new Set(names)];
}

function tokenNameForUrl(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return undefined;
  }
  const urlText = `${parsed.host}${parsed.pathname}`.toLowerCase();
  for (const [name, hints] of Object.entries(TOKEN_URL_HINTS)) {
    if (hints.some((hint) => urlText.includes(hint))) return name;
  }
  return undefined;
}

function tokenNameForPurpose(value: string | undefined): string | undefined {
  if (!value) return undefined;
  for (const [name, purposes] of Object.entries(TOKEN_PURPOSES)) {
    if (purposes.includes(value)) return name;
  }
  return undefined;
}

function stringHeaders(headers: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headers)
      .filter((entry): entry is [string, string] => typeof entry[1] === 'string')
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/**
 * Build the four copy-as-curl examples for the engineer door: an unauthenticated
 * metadata read, a claim-catalogue read with a published token, an evaluation
 * POST under a permitted purpose, and the skeptic's wrong-purpose POST that gets
 * a clean 403. URLs are rewritten to host-reachable origins through the same map
 * the rest of the site uses. The child benefit token is only inlined when it is
 * actually in the allowlist; otherwise the example references the env var name.
 */
export function buildCurlExamples(tokens: PublishedToken[]): CurlExample[] {
  const map = buildPublicUrlMap();
  const metadataUrl = mapPublicUrl('http://static-metadata:8080/metadata/catalog.json', map);
  const claimsUrl = mapPublicUrl('http://child-benefit-federator:8080/v1/claims', map);
  const evalUrl = mapPublicUrl('http://child-benefit-federator:8080/v1/evaluations', map);
  const published = tokens.find((token) => token.name === 'child-benefit-federator') ?? tokens.find((token) => token.name.includes('child'));
  const tokenValue = published?.token ?? '$CHILD_BENEFIT_FEDERATOR_TOKEN';
  const body =
    '{"target":{"type":"Person","identifiers":[{"scheme":"solmara_uin","value":"2300010248"}]},' +
    '"claims":["birth-is-registered"],"disclosure":"predicate",' +
    '"format":"application/vnd.solmara.federated-predicate-bundle+json"}';

  return [
    {
      id: 'metadata-get',
      title: 'Read the published metadata (no auth)',
      note: 'The metadata bundle is public. No token, no purpose header.',
      command: `curl -sS '${metadataUrl}'`
    },
    {
      id: 'claims-get',
      title: 'List the child benefit federation catalogue (published token)',
      note: 'The token is a synthetic lab credential scoped to the child benefit federator.',
      command: `curl -sS '${claimsUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n  -H 'Data-Purpose: ${CHILD_PURPOSE}'`
    },
    {
      id: 'evaluate-post',
      title: 'Collect source-owned predicates under a permitted purpose',
      note: 'A purpose-limited federation. The response contains predicates and peer traces, never source rows.',
      command:
        `curl -sS -X POST '${evalUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n` +
        `  -H 'Data-Purpose: ${CHILD_PURPOSE}' \\\n  -H 'Accept: application/vnd.solmara.federated-predicate-bundle+json' \\\n` +
        `  -H 'Content-Type: application/json' \\\n  -d '${body}'`
    },
    {
      id: 'wrong-purpose-post',
      title: 'Skeptic path: the same request under a wrong purpose',
      note: 'Ask under a purpose this federator does not permit and get a clean 403 with a stable problem code.',
      command:
        `curl -sS -X POST '${evalUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n` +
        `  -H 'Data-Purpose: ${PENSION_PURPOSE}' \\\n  -H 'Accept: application/vnd.solmara.federated-predicate-bundle+json' \\\n` +
        `  -H 'Content-Type: application/json' \\\n  -d '${body}'`
    }
  ];
}
