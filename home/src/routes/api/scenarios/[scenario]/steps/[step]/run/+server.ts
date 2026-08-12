import { json, error } from '@sveltejs/kit';
import { joinedUrl, runtime } from '$lib/server/runtime';
import { buildPublicUrlMap, mapPublicUrl } from '$lib/server/urlmap';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ fetch, params }) => {
  const response = await fetch(
    joinedUrl(runtime.scenarioRunnerUrl, `/v1/scenarios/${params.scenario}/steps/${params.step}/run`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    }
  );
  if (!response.ok) {
    throw error(response.status, 'scenario step unavailable');
  }
  const body = (await response.json()) as { result?: Record<string, unknown> };
  if (body && typeof body.result === 'object' && body.result) {
    body.result = safeResult(body.result);
  }
  return json(body);
};

function safeResult(result: Record<string, unknown>): Record<string, unknown> {
  const map = buildPublicUrlMap();
  const sourceTrace = Array.isArray(result.source_trace)
    ? result.source_trace.map(safePresentation).filter((item): item is Record<string, unknown> => item !== null)
    : [];
  return {
    step_id: stringValue(result.step_id),
    friendly: safeFriendly(result.friendly),
    request_source: safeRequest(result.request_source, map),
    request_sources: Array.isArray(result.request_sources)
      ? result.request_sources.map((source) => safeRequest(source, map))
      : undefined,
    response_source: safeResponse(result.response_source),
    source_trace: sourceTrace,
    results: safeResults(result.results),
    result_state: stringValue(result.result_state),
    presentation: safePresentation(result.presentation),
    presentations: Array.isArray(result.presentations)
      ? result.presentations.map(safePresentation).filter((item): item is Record<string, unknown> => item !== null)
      : undefined,
    credential: safeCredential(result.credential)
  };
}

function safeRequest(value: unknown, map: Record<string, string>): Record<string, unknown> {
  if (!isObject(value)) return {};
  const url = stringValue(value.url);
  return {
    method: stringValue(value.method),
    url: url ? mapPublicUrl(url, map) : undefined,
    purpose: stringValue(value.purpose),
    requests: Array.isArray(value.requests) ? value.requests.map((item) => safeRequest(item, map)) : undefined
  };
}

function safeResponse(value: unknown): Record<string, unknown> {
  if (!isObject(value)) return {};
  return {
    status: typeof value.status === 'number' ? value.status : null,
    code: stringValue(value.code),
    type: stringValue(value.type)
  };
}

function safePresentation(value: unknown): Record<string, unknown> | null {
  if (!isObject(value)) return null;
  const source = value.source === 'immutable extract' || value.source === 'Relay lookup' ? value.source : undefined;
  if (!stringValue(value.authority) || !stringValue(value.issuer) || !source) return null;
  return {
    authority: stringValue(value.authority),
    service_id: stringValue(value.service_id),
    issuer: stringValue(value.issuer),
    provider: stringValue(value.provider),
    source,
    status: typeof value.status === 'number' ? value.status : undefined,
    claims: Array.isArray(value.claims) ? value.claims.filter((item): item is string => typeof item === 'string') : undefined
  };
}

function safeResults(value: unknown): Record<string, unknown>[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.filter(isObject).map((item) => ({
    claim_id: stringValue(item.claim_id),
    concept_id: stringValue(item.concept_id),
    satisfied: typeof item.satisfied === 'boolean' ? item.satisfied : null,
    value: typeof item.value === 'boolean' ? item.value : undefined
  }));
}

function safeFriendly(value: unknown): Record<string, unknown> {
  if (!isObject(value)) return { title: 'Result unavailable.', message: '', status: 'needs_attention', facts: [] };
  return {
    title: stringValue(value.title),
    message: stringValue(value.message),
    status: stringValue(value.status),
    facts: Array.isArray(value.facts)
      ? value.facts.filter(isObject).map((fact) => ({ label: stringValue(fact.label), value: safeFact(fact.value) }))
      : []
  };
}

function safeCredential(value: unknown): Record<string, unknown> | undefined {
  if (!isObject(value)) return undefined;
  return {
    status: stringValue(value.status),
    profile: stringValue(value.profile),
    format: stringValue(value.format),
    vct: stringValue(value.vct),
    issuer: stringValue(value.issuer),
    disclosures: typeof value.disclosures === 'number' ? value.disclosures : undefined,
    reason: stringValue(value.reason),
    http_status: typeof value.http_status === 'number' ? value.http_status : null,
    message: stringValue(value.message)
  };
}

function safeFact(value: unknown): string | number | boolean | null {
  return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' ? value : null;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
