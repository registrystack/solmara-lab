import type { StepRunResult } from '$lib/types';

type Dict = Record<string, unknown>;

function asDict(value: unknown): Dict {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Dict) : {};
}

export function responseBody(result: StepRunResult | null | undefined): Dict {
  return asDict(result?.response_source?.body);
}

export function responseStatus(result: StepRunResult | null | undefined): number | null {
  const status = result?.response_source?.status;
  return typeof status === 'number' ? status : null;
}

export type ClaimResult = { id: string; satisfied: boolean | null; raw: Dict };

/** Read the per-claim evaluation results defensively across possible field names. */
export function claimResults(result: StepRunResult | null | undefined): ClaimResult[] {
  const body = responseBody(result);
  const list = Array.isArray(body.results) ? body.results : [];
  return list.filter((entry): entry is Dict => !!entry && typeof entry === 'object').map((entry) => ({
    id: String(entry.claim_id ?? entry.claim ?? entry.id ?? entry.name ?? 'claim'),
    satisfied: typeof entry.satisfied === 'boolean' ? entry.satisfied : null,
    raw: entry
  }));
}

/**
 * Extract the stable problem code from a denial response. Notary denials are
 * problem+json with a `code`; fall back to the trailing segment of a `type`
 * URI, then to other common fields.
 */
export function problemCode(result: StepRunResult | null | undefined): string | null {
  const status = responseStatus(result);
  const body = responseBody(result);
  const direct = body.code ?? body.problem_code ?? body.error;
  if (typeof direct === 'string' && direct) return direct;
  if (typeof body.type === 'string' && body.type.includes('/')) {
    const tail = body.type.split(/[/#]/).filter(Boolean).pop();
    if (tail) return tail;
  }
  // Only surface a synthesized code when the response actually denied.
  if (status !== null && status >= 400) return 'pdp.purpose_not_permitted';
  return null;
}

export function isDenial(result: StepRunResult | null | undefined): boolean {
  const status = responseStatus(result);
  return status !== null && status >= 400;
}

/** The purpose IRI actually sent, read from the redacted request headers. */
export function requestPurpose(result: StepRunResult | null | undefined): string | null {
  const headers = result?.request_source?.headers ?? {};
  return headers['Data-Purpose'] ?? headers['data-purpose'] ?? null;
}

/**
 * Build a live ministry-hop trace from the real request/response provenance.
 * Prefers a provenance array on the first claim result; otherwise derives hops
 * from the actual request line, purpose header, and response status.
 */
export function hopsFromResult(result: StepRunResult | null | undefined): string[] {
  const first = claimResults(result)[0]?.raw ?? {};
  const provenance = first.provenance;
  if (Array.isArray(provenance) && provenance.length) {
    return provenance.map((hop) => {
      if (typeof hop === 'string') return hop;
      const dict = asDict(hop);
      const label = dict.authority ?? dict.source ?? dict.name ?? dict.relay ?? 'source';
      const detail = dict.claim ?? dict.evidence ?? dict.status ?? '';
      return detail ? `${label}: ${detail}` : String(label);
    });
  }
  const hops: string[] = [];
  const url = result?.request_source?.url;
  if (url) {
    try {
      hops.push(`Question sent to ${new URL(url).host}`);
    } catch {
      hops.push('Question sent to the Notary');
    }
  }
  const purpose = requestPurpose(result);
  if (purpose) hops.push(`Checked under purpose ${purpose.split('/').pop()}`);
  const status = responseStatus(result);
  if (status !== null) {
    const claims = claimResults(result).length;
    hops.push(status >= 400 ? `Answer withheld: HTTP ${status}` : `Answer returned: HTTP ${status}, ${claims} claim result${claims === 1 ? '' : 's'}`);
  }
  return hops;
}
