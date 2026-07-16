import { env } from '$env/dynamic/private';
import { buildPublicUrlMap, mapPublicUrl } from './urlmap';
import type { CurlExample, PublishedToken } from '$lib/types';

const CHILD_PURPOSE = 'https://id.registrystack.org/solmara/purpose/child-benefit-review';
const PENSION_PURPOSE = 'https://id.registrystack.org/solmara/purpose/pension-payment-review';
const SURVIVOR_PURPOSE = 'https://id.registrystack.org/solmara/purpose/survivor-benefit-determination';
const VOUCHER_PURPOSE = 'https://id.registrystack.org/solmara/purpose/voucher-eligibility-review';
const LIVESTOCK_PURPOSE = 'https://id.registrystack.org/solmara/purpose/livestock-movement-control';
const CITIZEN_PURPOSE = 'https://id.registrystack.org/solmara/purpose/citizen-self-service';

const TOKEN_BINDINGS: Record<string, { urlHints: string[]; purposes: string[] }> = {
  'child-benefit-federator': {
    urlHints: ['child-benefit-federator', 'localhost:4321', '127.0.0.1:4321'],
    purposes: [CHILD_PURPOSE]
  },
  'cra-pension-client': {
    urlHints: ['cra-notary', 'localhost:4325', '127.0.0.1:4325'],
    purposes: [PENSION_PURPOSE]
  },
  'cra-citizen-client': {
    urlHints: ['cra-notary', 'localhost:4325', '127.0.0.1:4325'],
    purposes: [CITIZEN_PURPOSE]
  },
  'nia-citizen-client': {
    urlHints: ['nia-notary', 'localhost:4326', '127.0.0.1:4326'],
    purposes: [CITIZEN_PURPOSE]
  },
  'sipf-pension-client': {
    urlHints: ['sipf-notary', 'localhost:4322', '127.0.0.1:4322'],
    purposes: [PENSION_PURPOSE, SURVIVOR_PURPOSE]
  },
  'nagdi-notary': {
    urlHints: ['nagdi-notary', 'localhost:4323', '127.0.0.1:4323'],
    purposes: [VOUCHER_PURPOSE, LIVESTOCK_PURPOSE]
  }
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
  'cra-pension-client': {
    purpose: PENSION_PURPOSE,
    note: 'Scoped to CRA civil evidence used during pension payment review.'
  },
  'cra-citizen-client': {
    purpose: CITIZEN_PURPOSE,
    note: 'Scoped to CRA civil evidence used by citizen self-service.'
  },
  'nia-citizen-client': {
    purpose: CITIZEN_PURPOSE,
    note: 'Scoped to NIA population evidence and credential issuance used by citizen self-service.'
  },
  'sipf-pension-client': {
    purpose: PENSION_PURPOSE,
    note: 'Scoped to SIPF evidence for pension payment and survivor benefit review.'
  },
  'nagdi-notary': {
    purpose: VOUCHER_PURPOSE,
    note: 'Scoped to the NAgDI notary for farmer voucher and livestock movement review.'
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
  if (Array.isArray(clone.request_sources)) {
    clone.request_sources = clone.request_sources.map((source) => publishRequestSourceToken(source, published));
  }
  if (Array.isArray(clone.source_trace)) {
    clone.source_trace = clone.source_trace.map((item) => {
      if (!isObject(item)) return item;
      return { ...item, request_source: publishRequestSourceToken(item.request_source, published) };
    });
  }
  return clone as T;
}

function publishRequestSourceToken(source: unknown, published: Map<string, string>): unknown {
  if (!isObject(source)) return source;
  const headers = isObject(source.headers) ? stringHeaders(source.headers) : {};
  const purpose = Object.entries(headers).find(([name]) => name.toLowerCase() === 'data-purpose')?.[1];
  const token = tokenCandidates(source.url, purpose)
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
  const urlNames = tokenNamesForUrl(url);
  const purposeNames = tokenNamesForPurpose(purpose);
  const exactNames = urlNames.filter((name) => purposeNames.includes(name));
  return exactNames.length === 1 ? exactNames : [];
}

function tokenNamesForUrl(value: unknown): string[] {
  if (typeof value !== 'string') return [];
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return [];
  }
  const urlText = `${parsed.host}${parsed.pathname}`.toLowerCase();
  return Object.entries(TOKEN_BINDINGS)
    .filter(([, binding]) => binding.urlHints.some((hint) => urlText.includes(hint)))
    .map(([name]) => name);
}

function tokenNamesForPurpose(value: string | undefined): string[] {
  if (!value) return [];
  return Object.entries(TOKEN_BINDINGS)
    .filter(([, binding]) => binding.purposes.includes(value))
    .map(([name]) => name);
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
    '"format":"application/json"}';

  return [
    {
      id: 'metadata-get',
      title: 'Read the published metadata (no auth)',
      note: 'The metadata bundle is public. No token, no purpose header.',
      command: `curl -sS '${metadataUrl}'`
    },
    {
      id: 'claims-get',
      title: 'List the child benefit evidence catalogue (published token)',
      note: 'The token is a synthetic lab credential scoped to the child benefit federator.',
      command: `curl -sS '${claimsUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n  -H 'Data-Purpose: ${CHILD_PURPOSE}'`
    },
    {
      id: 'evaluate-post',
      title: 'Collect source-owned predicates under a permitted purpose',
      note: 'The application collects purpose-limited predicates and a source trace, never source rows.',
      command:
        `curl -sS -X POST '${evalUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n` +
        `  -H 'Data-Purpose: ${CHILD_PURPOSE}' \\\n  -H 'Accept: application/json' \\\n` +
        `  -H 'Content-Type: application/json' \\\n  -d '${body}'`
    },
    {
      id: 'wrong-purpose-post',
      title: 'Skeptic path: the same request under a wrong purpose',
      note: 'Ask under a purpose this evidence collector does not permit and get a clean 403 with a stable problem code.',
      command:
        `curl -sS -X POST '${evalUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n` +
        `  -H 'Data-Purpose: ${PENSION_PURPOSE}' \\\n  -H 'Accept: application/json' \\\n` +
        `  -H 'Content-Type: application/json' \\\n  -d '${body}'`
    }
  ];
}
