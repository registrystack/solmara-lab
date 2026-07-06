import { json, error } from '@sveltejs/kit';
import { readPurposes } from '$lib/server/data';
import { joinedUrl, runtime } from '$lib/server/runtime';
import { buildPublicUrlMap, rewriteRequestUrls } from '$lib/server/urlmap';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ fetch, params, request }) => {
  const payload = await runnerPayload(request);
  const response = await fetch(
    joinedUrl(runtime.scenarioRunnerUrl, `/v1/scenarios/${params.scenario}/steps/${params.step}/run`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }
  );
  if (!response.ok) {
    throw error(response.status, 'scenario step unavailable');
  }
  const body = (await response.json()) as { result?: Record<string, unknown> };
  if (body && typeof body.result === 'object' && body.result) {
    body.result = rewriteRequestUrls(body.result, buildPublicUrlMap());
  }
  return json(body);
};

async function runnerPayload(request: Request): Promise<Record<string, unknown>> {
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    return {};
  }
  if (!isObject(body) || typeof body.purpose !== 'string' || !body.purpose) {
    return {};
  }
  const allowedPurposes = await readPurposes();
  if (!allowedPurposes.some((purpose) => purpose.iri === body.purpose)) {
    throw error(400, 'unsupported purpose');
  }
  return { config: { purpose_override: body.purpose } };
}

function isObject(value: unknown): value is { purpose?: unknown } {
  return typeof value === 'object' && value !== null;
}
