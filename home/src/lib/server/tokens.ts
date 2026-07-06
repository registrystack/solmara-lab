import { env } from '$env/dynamic/private';
import { buildPublicUrlMap, mapPublicUrl } from './urlmap';
import type { CurlExample, PublishedToken } from '$lib/types';

const CHILD_PURPOSE = 'https://id.registrystack.org/solmara/purpose/child-benefit-review';
const PENSION_PURPOSE = 'https://id.registrystack.org/solmara/purpose/pension-payment-review';

/**
 * Notes and purposes for the names the lab deliberately publishes. Only names in
 * `HOME_PUBLISHED_TOKENS` are ever surfaced; this map only supplies copy.
 */
const TOKEN_NOTES: Record<string, { purpose: string; note: string }> = {
  'child-benefit-notary': {
    purpose: CHILD_PURPOSE,
    note: 'Scoped to the child benefit notary. Use it to read the claim catalogue and run evaluations under child-benefit-review.'
  },
  'pension-notary': {
    purpose: PENSION_PURPOSE,
    note: 'Scoped to the pension notary for pension stop and survivor benefit review.'
  },
  'nagdi-notary': {
    purpose: 'https://id.registrystack.org/solmara/purpose/voucher-eligibility-review',
    note: 'Scoped to the NAgDI notary for farmer voucher and livestock movement review.'
  },
  'citizen-notary': {
    purpose: 'https://id.registrystack.org/solmara/purpose/citizen-self-service',
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
  const claimsUrl = mapPublicUrl('http://child-benefit-notary:8080/v1/claims', map);
  const evalUrl = mapPublicUrl('http://child-benefit-notary:8080/v1/evaluations', map);
  const published = tokens.find((token) => token.name.includes('child'));
  const tokenValue = published?.token ?? '$CHILD_BENEFIT_NOTARY_TOKEN';
  const body =
    '{"target":{"type":"Person","identifiers":[{"scheme":"solmara_uin","value":"2300010248"}]},' +
    '"claims":["birth-is-registered"],"disclosure":"predicate",' +
    '"format":"application/vnd.registry-notary.claim-result+json"}';

  return [
    {
      id: 'metadata-get',
      title: 'Read the published metadata (no auth)',
      note: 'The metadata bundle is public. No token, no purpose header.',
      command: `curl -sS '${metadataUrl}'`
    },
    {
      id: 'claims-get',
      title: 'List a notary claim catalogue (published token)',
      note: 'The token is a synthetic lab credential scoped to this notary.',
      command: `curl -sS '${claimsUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n  -H 'Data-Purpose: ${CHILD_PURPOSE}'`
    },
    {
      id: 'evaluate-post',
      title: 'Evaluate a claim under a permitted purpose',
      note: 'A purpose-limited evaluation. The notary answers with predicates, never source rows.',
      command:
        `curl -sS -X POST '${evalUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n` +
        `  -H 'Data-Purpose: ${CHILD_PURPOSE}' \\\n  -H 'Content-Type: application/json' \\\n  -d '${body}'`
    },
    {
      id: 'wrong-purpose-post',
      title: 'Skeptic path: the same request under a wrong purpose',
      note: 'Ask under a purpose this notary does not permit and get a clean 403 with a stable problem code.',
      command:
        `curl -sS -X POST '${evalUrl}' \\\n  -H 'x-api-key: ${tokenValue}' \\\n` +
        `  -H 'Data-Purpose: ${PENSION_PURPOSE}' \\\n  -H 'Content-Type: application/json' \\\n  -d '${body}'`
    }
  ];
}
