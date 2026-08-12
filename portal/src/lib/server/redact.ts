// Server boundary helpers. Raw bodies are intentionally not projectable into a
// ProofTrace. These functions retain only transport status and scrub defensive
// text fields before an SSE frame is serialized.

const SOLMARA_UIN_RE = /\b[2-9]\d{9}\b/g;
const CASE_REFERENCE_RE = /\bCP-\d+\b/g;
const FARMER_ID_RE = /\bFR-\d+\b/g;
const BEARER_RE = /Bearer\s+[A-Za-z0-9._~+/=-]+/gi;
const API_KEY_RE = /(x-api-key\s*[:=]\s*)[A-Za-z0-9._~+/=-]+/gi;
const PRIVATE_KEY_RE = /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g;
const COMPACT_JWS_RE = /\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b/g;

export const PROOF_ALLOWLIST = [
  'claim',
  'purpose',
  'disclosure',
  'authority',
  'issuer',
  'serviceId',
  'source',
  'result',
  'freshness'
] as const;

export function scrubString(input: string): string {
  return input
    .replace(PRIVATE_KEY_RE, '[private key redacted]')
    .replace(BEARER_RE, 'Bearer [redacted]')
    .replace(API_KEY_RE, '$1[redacted]')
    .replace(COMPACT_JWS_RE, '[JWS redacted]')
    .replace(SOLMARA_UIN_RE, '[redacted]')
    .replace(CASE_REFERENCE_RE, '[redacted]')
    .replace(FARMER_ID_RE, '[redacted]');
}

export type RedactedRequest = {
  method: string;
  url: string;
};

export type RedactedResponse = {
  status: number;
};

export function redactBody(_body: unknown): Record<string, never> {
  return {};
}

export function redactRequest(request: {
  method: string;
  url: string;
  body?: unknown;
}): RedactedRequest {
  return { method: scrubString(request.method), url: scrubString(request.url) };
}

export function redactResponse(response: {
  status: number;
  body?: unknown;
}): RedactedResponse {
  return { status: response.status };
}

export function containsRawIdentifier(serialized: string): boolean {
  return (
    /\b[2-9]\d{9}\b/.test(serialized) ||
    /\bCP-\d+\b/.test(serialized) ||
    /\bFR-\d+\b/.test(serialized) ||
    /Bearer\s+[A-Za-z0-9._~+/=-]{8,}/i.test(serialized) ||
    /x-api-key\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}/i.test(serialized) ||
    /-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(serialized) ||
    /\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b/.test(serialized)
  );
}

export function pickAllowedMeta(meta: Record<string, unknown>): Record<string, unknown> {
  const allow = new Set<string>(PROOF_ALLOWLIST);
  return Object.fromEntries(
    Object.entries(meta)
      .filter(([key]) => allow.has(key))
      .map(([key, value]) => [key, typeof value === 'string' ? scrubString(value) : value])
  );
}
