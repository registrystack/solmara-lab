import type { EvaluateContext, DetailedEvidenceProvider } from '$lib/providers/EvidenceProvider';
import type { ClaimResult, Field, ProofTrace } from '$lib/types';
import { SCENARIOS, type EvaluateOptions, type MockEvaluation } from '$lib/providers/mock';

export type LiveProviderEnv = {
  SCENARIO_RUNNER_URL?: string;
};

type Fetcher = typeof fetch;
type Dict = Record<string, unknown>;
type RunnerResult = {
  friendly?: { status?: string; title?: string; message?: string };
  request_source?: Dict;
  request_sources?: Dict[];
  response_source?: { status?: number | null; body?: unknown; error?: string };
  source_trace?: Dict[];
  derived_decisions?: Record<string, boolean | null>;
};
type RunnerCall = { scenarioId: string; stepId: string };

/**
 * The live portal delegates scenario execution to the server-side scenario
 * runner. That runner owns Mint authentication and calls Registry Evidence;
 * browser-controlled input can select only a reviewed portal field.
 */
export class LiveEvidenceProvider implements DetailedEvidenceProvider {
  #seq = 0;
  #runnerUrl: string | undefined;
  #fetch: Fetcher;

  constructor(env: LiveProviderEnv, fetcher: Fetcher = fetch) {
    this.#runnerUrl = env.SCENARIO_RUNNER_URL;
    this.#fetch = fetcher;
  }

  async evaluate(field: Field, ctx: EvaluateContext, opts?: EvaluateOptions): Promise<ClaimResult> {
    return (await this.evaluateDetailed(field, ctx, opts)).result;
  }

  async evaluateDetailed(
    field: Field,
    _ctx: EvaluateContext,
    opts?: EvaluateOptions
  ): Promise<MockEvaluation> {
    const scenarioKey = opts?.scenarioKey ?? field.id;
    const scenario = SCENARIOS[scenarioKey];
    if (!scenario) throw new Error(`LiveEvidenceProvider: no scenario mapping for field "${field.id}"`);

    if (scenarioKey === 'denial') return this.#blocked(field, scenario, 'not_authorized');
    if (scenario.delegated && opts?.guardianLinkVerified !== true) {
      return this.#blocked(field, scenario, 'relationship_not_proven');
    }

    const calls = runnerCalls(scenarioKey, scenario.service);
    const responses = await Promise.all(calls.map((call) => this.#run(call)));
    const status = responses.find((response) => !isSuccess(response.response_source?.status))?.response_source?.status ?? 200;
    const results = responses.flatMap((response) => responseResults(response));
    const outcome = outcomeFor(scenarioKey, scenario.claimId, results, responses);
    const proofStatus = status === 403 ? 'denied' : !isSuccess(status) || !outcome.found ? 'error' : outcome.satisfied === false ? 'false' : 'ok';
    const seq = ++this.#seq;
    const applicationOwned = scenario.applicationOwned === true;
    const responseBody = {
      results,
      signed_evidence: responses.flatMap((response) => signedEvidence(response)),
      source_trace: responses.flatMap((response) => response.source_trace ?? []),
      ...(outcome.derivedDecisions ? { derived_decisions: outcome.derivedDecisions } : {})
    };
    const requestBody = {
      purpose: scenario.purpose,
      scenario_steps: calls.map((call) => `${call.scenarioId}/${call.stepId}`),
      composition: calls.length > 1 ? 'portal-application' : 'single-reviewed-step'
    };
    const display = proofStatus === 'ok' && outcome.satisfied === true
      ? scenario.display
      : `${scenario.claimId}: ${outcome.found ? String(outcome.value) : 'not returned'}`;

    return {
      result: {
        state: proofStatus === 'ok' ? scenario.state : proofStatus === 'false' ? 'false' : 'error',
        display,
        ...(!applicationOwned ? { authority: scenario.authority } : {}),
        traceId: `event ${seq}`
      },
      raw: {
        request: {
          method: calls.length > 1 ? 'MULTI' : 'POST',
          url: `${requiredRunnerUrl(this.#runnerUrl)}/v1/scenarios`,
          body: requestBody
        },
        response: { status: typeof status === 'number' ? status : 503, body: responseBody }
      } as unknown as MockEvaluation['raw'],
      proof: {
        headline: scenario.headline,
        answered: outcome.found
          ? `Registry Evidence answered: ${scenario.claimId} = ${String(outcome.value)}`
          : 'Registry Evidence returned no usable value for this field',
        notDisclosed: scenario.notDisclosed,
        status: proofStatus,
        authority: applicationOwned ? undefined : scenario.authority,
        crypto: evidenceProof(responses)
      },
      timing: { latencyMs: 0, staggerOrder: scenario.staggerOrder, slow: false }
    };
  }

  async #run(call: RunnerCall): Promise<RunnerResult> {
    const url = `${requiredRunnerUrl(this.#runnerUrl)}/v1/scenarios/${call.scenarioId}/steps/${call.stepId}/run`;
    const response = await this.#fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ config: {} })
    });
    const envelope = asDict(await response.json().catch(() => ({})));
    const result = asDict(envelope.result) as RunnerResult;
    if (!response.ok && result.response_source === undefined) {
      return {
        response_source: {
          status: response.status,
          body: {
            type: 'https://registrystack.org/problems/evidence/service_unavailable',
            title: 'Registry Evidence is unavailable',
            status: response.status
          }
        }
      };
    }
    return result;
  }

  #blocked(
    field: Field,
    scenario: (typeof SCENARIOS)[string],
    code: string
  ): MockEvaluation {
    const seq = ++this.#seq;
    const body = {
      type: `urn:solmara:portal:problem:${code}`,
      title: 'Portal authorization denied the request',
      status: 403,
      detail: 'The portal stopped this request before source access.',
      operation: `denial:event-${seq}`
    };
    return {
      result: {
        state: 'error',
        display: code === 'relationship_not_proven' ? 'Denied: guardian link not proven' : scenario.display,
        reasonCode: code,
        traceId: `event ${seq}`
      },
      raw: {
        request: {
          method: 'POST',
          url: 'solmara://citizen-portal/blocked-before-evidence',
          body: { field: field.id, purpose: scenario.purpose, disclosure: scenario.disclosure }
        },
        response: { status: 403, body }
      } as unknown as MockEvaluation['raw'],
      proof: {
        headline: 'Portal authorization stopped the request before Registry Evidence was called',
        answered: `Portal authorization gate returned 403 ${code}`,
        notDisclosed: scenario.notDisclosed,
        status: 'denied',
        authority: undefined,
        crypto: {
          signedBy: 'Portal authorization gate; Registry Evidence was not called',
          algorithm: 'No evidence assertion was produced',
          issuerKey: 'Not applicable',
          holderBound: 'Portal session and server-selected subject',
          credential: 'No credential or evidence assertion returned',
          auditId: `denial:event-${seq}`
        }
      },
      timing: { latencyMs: 0, staggerOrder: scenario.staggerOrder, slow: false }
    };
  }
}

function runnerCalls(scenarioKey: string, service: string): RunnerCall[] {
  if (service === 'childBenefit') return [{ scenarioId: 'birth-to-child-benefit', stepId: 'positive' }];
  if (service === 'nagdi') return [{ scenarioId: 'farmer-climate-smart-voucher', stepId: 'positive' }];
  if (service === 'citizen') return [{ scenarioId: 'citizen-self-service', stepId: 'positive' }];
  if (scenarioKey === 'combined-support-eligibility') {
    return [
      { scenarioId: 'death-to-pension-survivor', stepId: 'stop-payment' },
      { scenarioId: 'death-to-pension-survivor', stepId: 'survivor-benefit' }
    ];
  }
  if (scenarioKey === 'functioning-assessment') {
    return [{ scenarioId: 'death-to-pension-survivor', stepId: 'survivor-benefit' }];
  }
  if (scenarioKey === 'stale' || scenarioKey === 'ambiguous') {
    return [{ scenarioId: 'death-to-pension-survivor', stepId: 'stale-control' }];
  }
  return [{ scenarioId: 'death-to-pension-survivor', stepId: 'stop-payment' }];
}

function responseResults(response: RunnerResult): Dict[] {
  const body = asDict(response.response_source?.body);
  return Array.isArray(body.results) ? body.results.map(asDict).filter((item) => Object.keys(item).length > 0) : [];
}

function signedEvidence(response: RunnerResult): unknown[] {
  const body = asDict(response.response_source?.body);
  const signed = body.signed_evidence;
  if (Array.isArray(signed)) return signed;
  return signed && typeof signed === 'object' ? [signed] : [];
}

function outcomeFor(
  scenarioKey: string,
  claimId: string,
  results: Dict[],
  responses: RunnerResult[]
): { found: boolean; satisfied: boolean | null; value: unknown; derivedDecisions?: Record<string, boolean | null> } {
  if (scenarioKey === 'disability-determination') {
    const value = responses[0]?.derived_decisions?.['pension-payment-should-stop'];
    return { found: typeof value === 'boolean', satisfied: value ?? null, value, derivedDecisions: { 'pension-payment-should-stop': value ?? null } };
  }
  if (scenarioKey === 'combined-support-eligibility') {
    const required = ['person-is-deceased', 'pension-payment-active', 'survivor-is-eligible'];
    const values = required.map((id) => results.find((item) => item.claim_id === id)?.satisfied);
    const found = values.every((value) => typeof value === 'boolean');
    const value = found ? values.every((item) => item === true) : null;
    return { found, satisfied: value, value, derivedDecisions: { [claimId]: value } };
  }
  if (scenarioKey === 'citizen-record-status') {
    const required = ['civil-record-linked', 'citizen-population-record-active'];
    const values = required.map((id) => results.find((item) => item.claim_id === id)?.satisfied);
    const found = values.every((value) => typeof value === 'boolean');
    const value = found ? values.every((item) => item === true) : null;
    return { found, satisfied: value, value, derivedDecisions: { 'citizen-self-service-ready': value } };
  }
  const effectiveClaim = scenarioKey === 'person-is-alive' || scenarioKey === 'ambiguous'
    ? 'person-is-deceased'
    : scenarioKey === 'stale'
      ? 'survivor-is-eligible'
      : claimId;
  const item = results.find((candidate) => candidate.claim_id === effectiveClaim);
  const value = item?.value ?? item?.satisfied;
  return { found: item !== undefined, satisfied: typeof item?.satisfied === 'boolean' ? item.satisfied : null, value };
}

function evidenceProof(responses: RunnerResult[]): NonNullable<ProofTrace['proof']> {
  const assertions = responses.flatMap(signedEvidence);
  return {
    signedBy: assertions.length ? 'Registry Evidence signed the returned assertion set' : 'No signed assertion was returned',
    algorithm: assertions.length ? 'Flattened JWS, ES256' : 'Not available',
    issuerKey: '/.well-known/evidence/jwks.json',
    holderBound: 'Mint requester identity, purpose, requirement, nonce, and selector',
    credential: 'Registry Evidence assertion, not an application credential',
    auditId: `${assertions.length} signed assertion${assertions.length === 1 ? '' : 's'}`
  };
}

function requiredRunnerUrl(value: string | undefined): string {
  if (!value) throw new Error('SCENARIO_RUNNER_URL is required for PORTAL_PROVIDER=live');
  try {
    return new URL(value).toString().replace(/\/$/, '');
  } catch {
    throw new Error('SCENARIO_RUNNER_URL must be an absolute URL');
  }
}

function asDict(value: unknown): Dict {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Dict : {};
}

function isSuccess(status: number | null | undefined): boolean {
  return typeof status === 'number' && status >= 200 && status < 300;
}
