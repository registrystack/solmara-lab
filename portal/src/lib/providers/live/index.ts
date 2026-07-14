import type { EvaluateContext, DetailedEvidenceProvider } from '$lib/providers/EvidenceProvider';
import type { ClaimResult, Field, ProofTrace } from '$lib/types';
import {
  SCENARIOS,
  PERSONA,
  type EvaluateOptions,
  type MockEvaluation
} from '$lib/providers/mock';
import { AUTHORITY_LABEL, NOTARY_SERVICE_ID } from '$lib/providers/mock/scenarios';
import {
  authorityPlan,
  isApplicationOwnedPlan,
  type AuthorityClient,
  type AuthorityPlan
} from '$lib/providers/authority-plan';
import {
  authorityLabel,
  buildChildBenefitRequest,
  buildEvaluationRequest,
  buildRawRequest,
  CLAIM_RESULT_FORMAT,
  makeEvaluationId,
  type ClaimResultView,
  type RawApplicationRequest,
  type RawApplicationResponse,
  type RawChildBenefitResponse,
  type RawEvaluateRequest,
  type RawEvaluationResponse,
  type RawProviderResponse
} from '$lib/providers/mock/wire';

export type LiveProviderEnv = {
  CHILD_BENEFIT_FEDERATOR_URL?: string;
  CHILD_BENEFIT_FEDERATOR_TOKEN?: string;
  CRA_NOTARY_URL?: string;
  CRA_PENSION_CLIENT_TOKEN?: string;
  CRA_CITIZEN_CLIENT_TOKEN?: string;
  NIA_NOTARY_URL?: string;
  NIA_CITIZEN_CLIENT_TOKEN?: string;
  SIPF_NOTARY_URL?: string;
  SIPF_PENSION_CLIENT_TOKEN?: string;
  NAGDI_NOTARY_URL?: string;
  NAGDI_NOTARY_TOKEN?: string;
};

type Fetcher = typeof fetch;
type LiveClient = 'childBenefit' | AuthorityClient;
type LiveServiceRef = { url?: string; token?: string; urlEnv: string; tokenEnv: string };
type DenialBody = { error: string; error_description: string };
type AuthorityEvaluation = {
  plan: AuthorityPlan;
  url: string;
  request: RawEvaluateRequest;
  status: number;
  response: RawEvaluationResponse;
};
type ConfiguredService = { url: string; token: string };
type EvaluationOutcome = {
  hasResult: boolean;
  satisfied: boolean | null;
  value: unknown;
  stale: boolean;
  issuedAt?: string;
  derivedDecisions?: Record<string, boolean | null>;
};

export class LiveEvidenceProvider implements DetailedEvidenceProvider {
  #seq = 0;
  #services: Record<LiveClient, LiveServiceRef>;
  #fetch: Fetcher;

  constructor(env: LiveProviderEnv, fetcher: Fetcher = fetch) {
    this.#services = {
      childBenefit: {
        url: env.CHILD_BENEFIT_FEDERATOR_URL,
        token: env.CHILD_BENEFIT_FEDERATOR_TOKEN,
        urlEnv: 'CHILD_BENEFIT_FEDERATOR_URL',
        tokenEnv: 'CHILD_BENEFIT_FEDERATOR_TOKEN'
      },
      craPension: {
        url: env.CRA_NOTARY_URL,
        token: env.CRA_PENSION_CLIENT_TOKEN,
        urlEnv: 'CRA_NOTARY_URL',
        tokenEnv: 'CRA_PENSION_CLIENT_TOKEN'
      },
      craCitizen: {
        url: env.CRA_NOTARY_URL,
        token: env.CRA_CITIZEN_CLIENT_TOKEN,
        urlEnv: 'CRA_NOTARY_URL',
        tokenEnv: 'CRA_CITIZEN_CLIENT_TOKEN'
      },
      niaCitizen: {
        url: env.NIA_NOTARY_URL,
        token: env.NIA_CITIZEN_CLIENT_TOKEN,
        urlEnv: 'NIA_NOTARY_URL',
        tokenEnv: 'NIA_CITIZEN_CLIENT_TOKEN'
      },
      sipfPension: {
        url: env.SIPF_NOTARY_URL,
        token: env.SIPF_PENSION_CLIENT_TOKEN,
        urlEnv: 'SIPF_NOTARY_URL',
        tokenEnv: 'SIPF_PENSION_CLIENT_TOKEN'
      },
      nagdi: {
        url: env.NAGDI_NOTARY_URL,
        token: env.NAGDI_NOTARY_TOKEN,
        urlEnv: 'NAGDI_NOTARY_URL',
        tokenEnv: 'NAGDI_NOTARY_TOKEN'
      }
    };
    this.#fetch = fetcher;
  }

  async evaluate(field: Field, ctx: EvaluateContext, opts?: EvaluateOptions): Promise<ClaimResult> {
    const evaluation = await this.evaluateDetailed(field, ctx, opts);
    return evaluation.result;
  }

  async evaluateDetailed(
    field: Field,
    ctx: EvaluateContext,
    opts?: EvaluateOptions
  ): Promise<MockEvaluation> {
    const scenarioKey = opts?.scenarioKey ?? field.id;
    const scenario = SCENARIOS[scenarioKey];
    if (!scenario) {
      throw new Error(`LiveEvidenceProvider: no scenario mapping for field "${field.id}"`);
    }

    if (scenarioKey === 'denial') {
      return this.#denied(scenarioKey, scenario, ctx, 'subject_mismatch');
    }
    if (scenario.delegated && opts?.guardianLinkVerified !== true) {
      return this.#denied(scenarioKey, scenario, ctx, 'relationship_not_proven');
    }

    const seq = ++this.#seq;
    const subject = resolveSubject(scenarioKey, scenario, ctx);
    if (scenario.service === 'childBenefit') {
      return this.#evaluateChild(scenario, subject, seq);
    }

    const plan = authorityPlan(scenarioKey, scenario);
    const configured = plan.map((authority) => ({
      authority,
      service: this.#serviceFor(authority.client)
    }));
    const evaluations = await Promise.all(
      configured.map(({ authority, service }) =>
        this.#evaluateAuthority(authority, subject, service)
      )
    );
    const normalizedResults = evaluations.flatMap((evaluation) => evaluation.response.results);
    const outcome = evaluationOutcome(scenarioKey, scenario, normalizedResults);
    const failed = evaluations.find(
      (evaluation) => evaluation.status < 200 || evaluation.status >= 300
    );
    const responseStatus = failed?.status ?? 200;
    const status = proofStatus(responseStatus, outcome.satisfied, outcome.hasResult);
    const raw = liveRawTrace(evaluations, outcome.derivedDecisions);
    const applicationOwned = isApplicationOwnedPlan(plan);

    return {
      result: portalResult(scenario, status, outcome, seq),
      raw,
      proof: {
        headline: scenario.headline,
        answered: answeredByAuthorities(evaluations),
        notDisclosed: scenario.notDisclosed,
        status,
        authority: applicationOwned ? undefined : scenario.notary,
        crypto: liveCrypto(scenarioKey, evaluations)
      },
      timing: { latencyMs: 0, staggerOrder: scenario.staggerOrder, slow: false }
    };
  }

  async #evaluateChild(
    scenario: (typeof SCENARIOS)[string],
    subject: string,
    seq: number
  ): Promise<MockEvaluation> {
    const service = this.#serviceFor('childBenefit');
    const request = buildChildBenefitRequest(scenario, subject);
    const url = joinedUrl(service.url, '/v1/evaluations');
    const response = await this.#fetchJson(url, {
      method: 'POST',
      headers: {
        ...notaryHeaders(service.token, scenario.purpose, 'application/json'),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(request)
    });
    const childBody =
      isChildBenefitResponse(response.body) && response.body.purpose === scenario.purpose
        ? response.body
        : undefined;
    const claim = childBody?.results.find((result) => result.claim_id === scenario.claimId);
    const attributed =
      childBody !== undefined && claim !== undefined && hasChildAttribution(childBody, scenario);
    const stale = attributed && isExpired(claim.expires_at);
    const outcome: EvaluationOutcome = {
      hasResult: attributed,
      satisfied: attributed && !stale ? claim.satisfied : null,
      value: attributed && !stale ? claim.satisfied : undefined,
      stale,
      issuedAt: attributed ? claim.issued_at : undefined
    };
    const status = proofStatus(response.status, outcome.satisfied, outcome.hasResult);
    const evidenceSetId = childBody?.evidence_set_id;
    const responseBody: RawProviderResponse = childBody ?? { results: [] };

    return {
      result: portalResult(scenario, status, outcome, seq),
      raw: {
        request: { method: 'POST', url, body: request },
        response: { status: response.status, body: responseBody }
      },
      proof: {
        headline: scenario.headline,
        answered: childAnswered(attributed ? childBody : undefined, scenario.claimId),
        notDisclosed: scenario.notDisclosed,
        status,
        authority: scenario.notary,
        crypto: {
          signedBy: `No application signature; ${authorityLabel(scenario)} source result was collected by child-benefit-federator`,
          algorithm: 'Ordinary JSON response; no application signature asserted',
          issuerKey: 'Not applicable for an application evidence set',
          holderBound: 'Not credential-bound; the BFF selected the purpose and subject',
          credential: 'Minimized source-attributed predicate result',
          auditId: `evidence-set:${evidenceSetId ?? 'unavailable'}`
        }
      },
      timing: { latencyMs: 0, staggerOrder: scenario.staggerOrder, slow: false }
    };
  }

  async #evaluateAuthority(
    plan: AuthorityPlan,
    subject: string,
    service: ConfiguredService
  ): Promise<AuthorityEvaluation> {
    const request = buildEvaluationRequest(
      plan.claimId,
      subject,
      plan.purpose,
      plan.scheme ?? 'solmara_uin'
    );
    const url = joinedUrl(service.url, '/v1/evaluations');
    const response = await this.#fetchJson(url, {
      method: 'POST',
      headers: {
        ...notaryHeaders(service.token, plan.purpose, CLAIM_RESULT_FORMAT),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(request)
    });
    return {
      plan,
      url,
      request,
      status: response.status,
      response: parseEvaluationResponse(response.body, plan)
    };
  }

  async #fetchJson(
    url: string,
    init: RequestInit
  ): Promise<{ status: number; body: Record<string, unknown> }> {
    const response = await this.#fetch(url, init);
    const body: unknown = await response.json().catch(() => ({}));
    return { status: response.status, body: recordValue(body) ?? {} };
  }

  #serviceFor(client: LiveClient): { url: string; token: string } {
    const ref = this.#services[client];
    return {
      url: requiredUrl(ref.url, ref.urlEnv),
      token: requiredValue(ref.token, ref.tokenEnv)
    };
  }

  #denied(
    scenarioKey: string,
    scenario: (typeof SCENARIOS)[string],
    ctx: EvaluateContext,
    code: string
  ): MockEvaluation {
    const seq = ++this.#seq;
    const evaluationId = makeEvaluationId(seq);
    const subject =
      scenarioKey === 'denial'
        ? PERSONA.karim
        : ctx.delegatedTarget ?? ctx.selectedSubject ?? ctx.subject;
    const rawRequest =
      scenario.service === 'childBenefit'
        ? buildChildBenefitRequest(scenario, subject)
        : buildRawRequest(scenario, subject, {
            actorIdHash: hashActor(ctx.subject),
            delegationRef: 'rnref:v1:REL-1001-MOTHER'
          });
    const body: DenialBody = {
      error: code,
      error_description: scenario.denial?.message ?? 'requester is not authorized for this target'
    };
    return {
      result: {
        state: 'error',
        display:
          code === 'relationship_not_proven'
            ? 'Denied: guardian link not proven, no dependent record was read'
            : scenario.display,
        reasonCode: code,
        traceId: `event ${seq}`
      },
      raw: {
        request: {
          method: 'POST',
          url: 'solmara://citizen-portal/blocked-before-authority-call',
          body: rawRequest
        },
        response: { status: 403, body }
      },
      proof: {
        headline:
          code === 'relationship_not_proven'
            ? `Portal denied the request before calling ${authorityLabel(scenario)}: the guardian link was not proven, so no dependent record was read`
            : 'Portal denied the cross-person request before any authority call',
        answered: `Portal authorization gate stopped the request before any authority call: 403 ${code}`,
        notDisclosed: scenario.notDisclosed,
        status: 'denied',
        authority: undefined,
        crypto: {
          signedBy: 'Portal authorization gate; no authority Notary called',
          algorithm: 'No signature; request stopped before source access',
          issuerKey: 'Not applicable',
          holderBound: 'Portal session actor and server-selected subject',
          credential: 'No credential or evidence result returned',
          auditId: `denial:${evaluationId}`
        }
      },
      timing: { latencyMs: 0, staggerOrder: scenario.staggerOrder, slow: false }
    };
  }
}

function evaluationOutcome(
  scenarioKey: string,
  scenario: (typeof SCENARIOS)[string],
  results: ClaimResultView[]
): EvaluationOutcome {
  if (scenarioKey === 'disability-determination') {
    return derivedOutcome(
      scenario.claimId,
      results,
      ['person-is-deceased', 'pension-payment-active']
    );
  }
  if (scenarioKey === 'combined-support-eligibility') {
    return derivedOutcome(
      scenario.claimId,
      results,
      ['person-is-deceased', 'pension-payment-active', 'survivor-is-eligible']
    );
  }
  if (scenarioKey === 'citizen-record-status') {
    return derivedOutcome(
      'citizen-self-service-ready',
      results,
      ['civil-record-linked', 'citizen-population-record-active']
    );
  }
  const claimId =
    scenarioKey === 'person-is-alive' || scenarioKey === 'ambiguous'
      ? 'person-is-deceased'
      : scenarioKey === 'functioning-assessment' ||
          scenarioKey === 'stale'
        ? 'survivor-is-eligible'
        : scenario.claimId;
  const result = results.find((candidate) => candidate.claim_id === claimId);
  const stale = result !== undefined && isExpired(result.expires_at);
  return {
    hasResult: result !== undefined,
    satisfied: stale ? null : (result?.satisfied ?? null),
    value: stale ? undefined : result?.value,
    stale,
    issuedAt: result?.issued_at
  };
}

function derivedOutcome(
  decisionId: string,
  results: ClaimResultView[],
  claims: string[],
  trueValue: unknown = true
): EvaluationOutcome {
  const sourceResults = claims.map((claimId) =>
    results.find((result) => result.claim_id === claimId)
  );
  const hasResult = sourceResults.every((result) => result !== undefined);
  const stale = hasResult && sourceResults.some((result) => result && isExpired(result.expires_at));
  const satisfied = hasResult && !stale
    ? sourceResults.every((result) => result?.satisfied === true)
    : null;
  return {
    hasResult,
    satisfied,
    value: satisfied === true ? trueValue : satisfied,
    stale,
    issuedAt: oldestIssuedAt(sourceResults),
    derivedDecisions: { [decisionId]: satisfied }
  };
}

function oldestIssuedAt(results: Array<ClaimResultView | undefined>): string | undefined {
  return results
    .flatMap((result) => (result ? [result.issued_at] : []))
    .sort((left, right) => Date.parse(left) - Date.parse(right))[0];
}

function isExpired(expiresAt: string | null, now = Date.now()): boolean {
  return expiresAt !== null && Date.parse(expiresAt) <= now;
}

function liveRawTrace(
  evaluations: AuthorityEvaluation[],
  derivedDecisions?: Record<string, boolean | null>
): MockEvaluation['raw'] {
  const first = evaluations[0];
  if (evaluations.length === 1 && first) {
    return {
      request: { method: 'POST', url: first.url, body: first.request },
      response: { status: first.status, body: first.response }
    };
  }
  const purposes = [...new Set(evaluations.map((evaluation) => evaluation.plan.purpose))];
  const request: RawApplicationRequest = {
    purpose:
      purposes.length === 1
        ? (purposes[0] ?? '')
        : 'application-composed-from-source-authorized-purposes',
    disclosure: 'decision',
    composition: 'application',
    requests: evaluations.map((evaluation) => ({
      authority: evaluation.plan.authority,
      service_id: evaluation.plan.serviceId,
      body: evaluation.request
    }))
  };
  const response: RawApplicationResponse = {
    schema_version: 'solmara-portal-evidence/v1',
    orchestration: {
      service_id: 'citizen-portal',
      decision: 'application_composed'
    },
    results: evaluations.flatMap((evaluation) => evaluation.response.results),
    source_trace: evaluations.map((evaluation) => ({
      authority: evaluation.plan.authority,
      service_id: evaluation.plan.serviceId,
      status: evaluation.status,
      claims: [evaluation.plan.claimId]
    })),
    ...(derivedDecisions ? { derived_decisions: derivedDecisions } : {})
  };
  const failed = evaluations.find(
    (evaluation) => evaluation.status < 200 || evaluation.status >= 300
  );
  return {
    request: {
      method: 'MULTI',
      url: 'solmara://citizen-portal/application-composition',
      body: request
    },
    response: { status: failed?.status ?? 200, body: response }
  };
}

function portalResult(
  scenario: (typeof SCENARIOS)[string],
  status: ProofTrace['status'],
  outcome: EvaluationOutcome,
  seq: number
): ClaimResult {
  const applicationOwned = outcome.derivedDecisions !== undefined;
  return {
    state:
      outcome.stale
        ? 'stale'
        : status === 'false'
        ? 'false'
        : status === 'denied' || status === 'error'
          ? 'error'
          : scenario.state,
    display: displayResult(scenario, outcome.value, outcome.satisfied, status, outcome.stale),
    ...(!applicationOwned ? { authority: scenario.notary } : {}),
    ...(outcome.issuedAt ? { asOf: outcome.issuedAt } : {}),
    traceId: `event ${seq}`
  };
}

function liveCrypto(
  _scenarioKey: string,
  evaluations: AuthorityEvaluation[]
): NonNullable<ProofTrace['proof']> {
  const evaluationIds = evaluations.flatMap((evaluation) =>
    evaluation.response.results.map((result) => result.evaluation_id)
  );
  const auditId =
    evaluationIds.length > 0
      ? evaluationIds.map((evaluationId) => `evaluation:${evaluationId}`).join('; ')
      : 'No valid evaluation identifier returned';
  const answeringAuthorities = [
    ...new Set(
      evaluations
        .filter((evaluation) => evaluation.response.results.length > 0)
        .map((evaluation) => evaluation.plan.authority)
    )
  ];
  if (evaluations.length > 1) {
    return {
      signedBy:
        answeringAuthorities.length > 0
          ? `No credential issued; ${answeringAuthorities.join(' and ')} returned separate claim evaluations`
          : 'No valid claim result returned; the portal did not compose a decision',
      algorithm: 'Independent Registry Notary claim-result responses',
      issuerKey: 'Not applicable for claim-result evaluation',
      holderBound: 'Not credential-bound; the BFF selected the purpose and subject',
      credential: 'Application decision only; no credential issued by the portal',
      auditId
    };
  }
  return {
    signedBy:
      answeringAuthorities.length === 1
        ? `No credential issued; ${answeringAuthorities[0]} returned a claim evaluation`
        : 'No valid claim result returned',
    algorithm: 'Source-owned Registry Notary claim-result responses',
    issuerKey: 'Not applicable for claim-result evaluation',
    holderBound: 'Not credential-bound; the BFF selected the purpose and subject',
    credential: 'Claim results only; no credential issued by the portal',
    auditId
  };
}

function resolveSubject(
  scenarioKey: string,
  scenario: (typeof SCENARIOS)[string],
  ctx: EvaluateContext
): string {
  if (scenarioKey === 'denial') return PERSONA.karim;
  if (scenario.delegated || scenarioKey === 'caregiver-link') {
    return requiredValue(ctx.delegatedTarget, 'delegatedTarget');
  }
  return ctx.selectedSubject ?? ctx.subject;
}

function requiredUrl(value: string | undefined, name: string): string {
  const raw = requiredValue(value, name);
  try {
    return new URL(raw).toString().replace(/\/$/, '');
  } catch {
    throw new Error(`${name} must be an absolute URL`);
  }
}

function requiredValue(value: string | undefined, name: string): string {
  if (!value) throw new Error(`${name} is required for PORTAL_PROVIDER=live`);
  return value;
}

function joinedUrl(base: string, path: string): string {
  return `${base.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}

function notaryHeaders(token: string, purpose: string, accept: string): Record<string, string> {
  return {
    'x-api-key': token,
    Accept: accept,
    'Data-Purpose': purpose
  };
}

function parseEvaluationResponse(
  body: Record<string, unknown>,
  expected: AuthorityPlan
): RawEvaluationResponse {
  if (!Array.isArray(body.results) || body.results.length !== 1) return { results: [] };
  const result = parseClaimResult(body.results[0]);
  if (
    !result ||
    result.claim_id !== expected.claimId ||
    result.provenance.generated_by.service_id !== expected.serviceId
  ) {
    return { results: [] };
  }
  return { results: [result] };
}

function parseClaimResult(value: unknown): ClaimResultView | undefined {
  const item = recordValue(value);
  if (!item) return undefined;
  const targetRef = parseTargetRef(item.target_ref);
  const provenance = parseProvenance(item.provenance);
  const expiresAt = item.expires_at;
  if (
    !nonEmptyString(item.evaluation_id) ||
    !nonEmptyString(item.claim_id) ||
    !nonEmptyString(item.claim_version) ||
    !nonEmptyString(item.subject_type) ||
    !targetRef ||
    !('value' in item) ||
    (typeof item.satisfied !== 'boolean' && item.satisfied !== null) ||
    item.disclosure !== 'predicate' ||
    item.format !== CLAIM_RESULT_FORMAT ||
    !dateTimeString(item.issued_at) ||
    (expiresAt !== null && !dateTimeString(expiresAt)) ||
    !validLifetime(item.issued_at, expiresAt) ||
    !provenance
  ) {
    return undefined;
  }
  if (
    provenance.generated_by.evaluation_id !== item.evaluation_id ||
    provenance.generated_by.claim_id !== item.claim_id ||
    provenance.generated_by.claim_version !== item.claim_version
  ) {
    return undefined;
  }
  return {
    evaluation_id: item.evaluation_id,
    claim_id: item.claim_id,
    claim_version: item.claim_version,
    subject_type: item.subject_type,
    target_ref: targetRef,
    value: item.value,
    satisfied: item.satisfied,
    disclosure: item.disclosure,
    format: item.format,
    issued_at: item.issued_at,
    expires_at: expiresAt,
    provenance
  };
}

function parseTargetRef(value: unknown): ClaimResultView['target_ref'] | undefined {
  const target = recordValue(value);
  if (!target || !nonEmptyString(target.handle)) return undefined;
  if (
    ('identifier_schemes' in target &&
      (!Array.isArray(target.identifier_schemes) ||
        !target.identifier_schemes.every(nonEmptyString))) ||
    ('profile' in target && !nonEmptyString(target.profile)) ||
    ('type' in target && !nonEmptyString(target.type))
  ) {
    return undefined;
  }
  return {
    handle: target.handle,
    ...(Array.isArray(target.identifier_schemes)
      ? { identifier_schemes: target.identifier_schemes }
      : {}),
    ...(typeof target.profile === 'string' ? { profile: target.profile } : {}),
    ...(typeof target.type === 'string' ? { type: target.type } : {})
  };
}

function parseProvenance(value: unknown): ClaimResultView['provenance'] | undefined {
  const provenance = recordValue(value);
  const generatedBy = recordValue(provenance?.generated_by);
  const used = recordValue(provenance?.used);
  if (
    provenance?.schema_version !== 'registry-notary-claim-provenance/v2' ||
    !generatedBy ||
    generatedBy.type !== 'claim_evaluation' ||
    !nonEmptyString(generatedBy.service_id) ||
    !nonEmptyString(generatedBy.evaluation_id) ||
    !nonEmptyString(generatedBy.claim_id) ||
    !nonEmptyString(generatedBy.claim_version) ||
    !validOptionalString(generatedBy, 'policy_hash') ||
    !validOptionalString(generatedBy, 'policy_id') ||
    !validOptionalString(generatedBy, 'policy_version') ||
    !used ||
    !Number.isInteger(used.relay_consultation_count) ||
    Number(used.relay_consultation_count) < 0 ||
    !Array.isArray(provenance.derived_from) ||
    !provenance.derived_from.every((entry) => recordValue(entry) !== undefined)
  ) {
    return undefined;
  }
  return {
    schema_version: 'registry-notary-claim-provenance/v2',
    generated_by: {
      type: 'claim_evaluation',
      service_id: generatedBy.service_id,
      evaluation_id: generatedBy.evaluation_id,
      claim_id: generatedBy.claim_id,
      claim_version: generatedBy.claim_version,
      ...(typeof generatedBy.policy_hash === 'string'
        ? { policy_hash: generatedBy.policy_hash }
        : {}),
      ...(typeof generatedBy.policy_id === 'string' ? { policy_id: generatedBy.policy_id } : {}),
      ...(typeof generatedBy.policy_version === 'string'
        ? { policy_version: generatedBy.policy_version }
        : {})
    },
    used: { relay_consultation_count: Number(used.relay_consultation_count) },
    derived_from: provenance.derived_from
  };
}

function isChildBenefitResponse(body: Record<string, unknown>): body is RawChildBenefitResponse {
  const orchestration = recordValue(body.orchestration);
  const target = recordValue(body.target);
  return (
    body.schema_version === 'solmara-child-benefit-evidence/v1' &&
    nonEmptyString(body.evidence_set_id) &&
    orchestration?.service_id === 'child-benefit-federator' &&
    orchestration.decision === 'not_composed' &&
    typeof body.purpose === 'string' &&
    target !== undefined &&
    !('identifiers' in target) &&
    Array.isArray(target.identifier_schemes) &&
    target.identifier_schemes.every((scheme) => typeof scheme === 'string') &&
    Array.isArray(body.results) &&
    body.results.every((item) => {
      const result = recordValue(item);
      return (
        result !== undefined &&
        nonEmptyString(result.claim_id) &&
        nonEmptyString(result.claim_version) &&
        typeof result.satisfied === 'boolean' &&
        result.disclosure === 'predicate' &&
        result.format === CLAIM_RESULT_FORMAT &&
        dateTimeString(result.issued_at) &&
        (dateTimeString(result.expires_at) || result.expires_at === null) &&
        validLifetime(result.issued_at, result.expires_at) &&
        nonEmptyString(result.authority) &&
        nonEmptyString(result.notary_service_id)
      );
    }) &&
    Array.isArray(body.source_trace)
  );
}

function hasChildAttribution(
  body: RawChildBenefitResponse,
  scenario: (typeof SCENARIOS)[string]
): boolean {
  const claimId = scenario.claimId;
  const expectedServiceId = NOTARY_SERVICE_ID[scenario.notary];
  const expectedAuthority = AUTHORITY_LABEL[scenario.notary];
  const result = body.results.find((candidate) => candidate.claim_id === claimId);
  if (!result) return false;
  if (
    result.notary_service_id !== expectedServiceId ||
    result.authority !== expectedAuthority
  ) {
    return false;
  }
  return body.source_trace.some((item) => {
    const trace = recordValue(item);
    return (
      trace?.service_id === expectedServiceId &&
      trace.authority === expectedAuthority &&
      Array.isArray(trace.claims) &&
      trace.claims.includes(claimId)
    );
  });
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return undefined;
  // TypeScript cannot infer the string-keyed record after the runtime object checks.
  return value as Record<string, unknown>;
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function dateTimeString(value: unknown): value is string {
  return (
    nonEmptyString(value) &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    !Number.isNaN(Date.parse(value))
  );
}

function validOptionalString(record: Record<string, unknown>, key: string): boolean {
  return !(key in record) || nonEmptyString(record[key]);
}

function validLifetime(issuedAt: unknown, expiresAt: unknown): boolean {
  if (!dateTimeString(issuedAt)) return false;
  if (expiresAt === null) return true;
  return dateTimeString(expiresAt) && Date.parse(expiresAt) >= Date.parse(issuedAt);
}

function proofStatus(
  status: number,
  satisfied: unknown,
  hasResult: boolean
): ProofTrace['status'] {
  if (status === 403) return 'denied';
  if (status < 200 || status >= 300 || !hasResult) return 'error';
  if (satisfied === false) return 'false';
  return satisfied === true ? 'ok' : 'error';
}

function displayResult(
  scenario: (typeof SCENARIOS)[string],
  value: unknown,
  satisfied: unknown,
  status: ProofTrace['status'],
  stale: boolean
): string {
  if (stale) {
    return scenario.state === 'stale'
      ? scenario.display
      : `${scenario.claimId}: expired evidence, refresh required`;
  }
  if (status === 'ok' && satisfied === true) return scenario.display;
  return `${scenario.claimId}: ${displayValue(value, satisfied)}`;
}

function displayValue(value: unknown, satisfied: unknown): string {
  if (typeof satisfied === 'boolean') return String(satisfied);
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (value === null || value === undefined) return 'not returned';
  return JSON.stringify(value);
}

function answeredByAuthorities(evaluations: AuthorityEvaluation[]): string {
  return evaluations
    .map((evaluation) => {
      const result = evaluation.response.results.find(
        (candidate) => candidate.claim_id === evaluation.plan.claimId
      );
      return `${evaluation.plan.authority} answered: ${evaluation.plan.claimId} = ${displayValue(result?.value, result?.satisfied)}`;
    })
    .join('; ');
}

function childAnswered(body: RawChildBenefitResponse | undefined, claimId: string): string {
  const result = body?.results.find((candidate) => candidate.claim_id === claimId);
  if (!result) return `Child benefit application returned no valid ${claimId} result`;
  return `${result.authority} answered: ${claimId} = ${result.satisfied}`;
}

function hashActor(subject: string): string {
  let hash = 0;
  for (let i = 0; i < subject.length; i += 1) {
    hash = (hash * 31 + subject.charCodeAt(i)) & 0xffffffff;
  }
  return `hmac-sha256:${(hash >>> 0).toString(16).padStart(8, '0')}`;
}
