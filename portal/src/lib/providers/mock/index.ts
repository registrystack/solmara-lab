// MockEvidenceProvider: the Phase 0 interaction-nailing layer behind the shared
// EvidenceProvider seam. Returns canned ClaimResults plus a matching ProofTrace
// per field/claim, with deterministic latency and a top-to-bottom stagger.
//
// The depth-2 request/response bodies inside each ProofTrace are built by ./wire
// from the current authority Evidence request and signed-assertion contracts.

import type { EvaluateContext, EvidenceProvider } from '$lib/providers/EvidenceProvider';
import type { ClaimResult, EvidencePresentation, EvidenceSource, Field, ProofStatus, ProofTrace } from '$lib/types';
import { evidencePresentation } from '$lib/fields/authorities';
import { PERSONA, SCENARIOS, type ScenarioResult } from './scenarios';
import {
  authorityPlan,
  isApplicationOwnedPlan,
  type AuthorityPlan
} from '$lib/providers/authority-plan';
import {
  authorityLabel,
  buildEvidenceAssertion,
  buildEvidenceRequest,
  buildRawRequest,
  buildRawResponse,
  evidenceUrl,
  makeOperationId,
  signEvidence,
  type RawApplicationRequest,
  type RawApplicationResponse,
  type RawProviderRequest
} from './wire';

// Optional knobs for delegated / denial selection the BFF passes via ctx-derived
// field hints. The provider never trusts a client-supplied subject; the BFF
// resolves the subject server-side and passes it in ctx.subject.
export type EvaluateOptions = {
  // explicit scenario override (state gallery / per-state trigger list). When set,
  // the field's normal mapping is bypassed so every UX state is reachable.
  scenarioKey?: string;
  // for delegated fields, whether the guardian-link hop has already succeeded.
  // The provider DENIES a dependent source read if this is false, proving the gate.
  guardianLinkVerified?: boolean;
};

// The richer evaluate result the BFF consumes: the portal-facing ClaimResult plus
// the raw server-only request/response and safe proof presentation. Raw values
// are never copied into the browser-facing ProofTrace.
export type MockEvaluation = {
  result: ClaimResult;
  raw: {
    request: { method: string; url: string; body: unknown };
    response: { status: number; body: unknown };
  };
  proof: {
    headline: string;
    answered: string;
    notDisclosed: string;
    status: ProofTrace['status'];
    authority: ProofTrace['authority'];
    purpose: string;
    presentations: EvidencePresentation[];
    crypto: NonNullable<ProofTrace['proof']>;
  };
  // deterministic timing for the UI stagger / SLOW threshold choreography.
  timing: { latencyMs: number; staggerOrder: number; slow: boolean };
};

type DenialBody = {
  type: string;
  title: string;
  status: number;
  detail: string;
  operation: string;
};

const SLOW_THRESHOLD_MS = 6000;

// Resolve a Field + ctx + options to a scenario key. The mapping is explicit so
// the demo's whole surface is driven by canned data.
export function resolveScenarioKey(field: Field, opts?: EvaluateOptions): string {
  if (opts?.scenarioKey) return opts.scenarioKey;
  // Field ids carry the canonical scenario key in the demo descriptors. Fall back
  // to the claim where the id is generic.
  if (field.id in SCENARIOS) return field.id;
  if (field.claim && field.claim in SCENARIOS) return field.claim;
  throw new Error(`MockEvidenceProvider: no canned scenario for field "${field.id}"`);
}

// Resolve the effective subject for a scenario. Story fixtures can bind to a
// named persona so mock and live provider requests stay aligned with generated
// Solmara fixtures.
function resolveSubject(scenario: ScenarioResult, ctx: EvaluateContext, key: string): string {
  if (key === 'denial') return PERSONA.karim;
  if (scenario.subjectPersona) return PERSONA[scenario.subjectPersona];
  if (scenario.authority === 'agri') return PERSONA.aminaFarmer;
  if (scenario.delegated) return ctx.delegatedTarget ?? PERSONA.mateo;
  return ctx.subject;
}

function buildCrypto(
  scenario: ScenarioResult,
  _evaluationId: string,
  plan: AuthorityPlan[]
): NonNullable<ProofTrace['proof']> {
  if (isApplicationOwnedPlan(plan)) {
    const authorities = [...new Set(plan.map((authority) => authority.authority))];
    return {
      signedBy: `${authorities.join(' and ')} returned separate authority Evidence assertions`,
      algorithm: 'Independent flattened JWS assertions, ES256',
      issuerKey: 'Each Evidence service publishes /.well-known/evidence/jwks.json',
      holderBound: 'Audience-scoped to the portal requester, purpose, nonce, and subject binding',
      credential: 'Signed minimum-disclosure assertions; the portal composed the decision',
    };
  }
  return {
    signedBy: `${authorityLabel(scenario)} Evidence`,
    algorithm: 'Flattened JWS, ES256',
    issuerKey: '/.well-known/evidence/jwks.json',
    holderBound: 'Audience-scoped to the portal requester, purpose, nonce, and subject binding',
    credential: 'Signed minimum-disclosure Evidence assertion'
  };
}

function blockedCrypto(_evaluationId: string): NonNullable<ProofTrace['proof']> {
  return {
    signedBy: 'Portal authorization gate; authority Evidence was not called',
    algorithm: 'No Evidence assertion was produced',
    issuerKey: 'Not applicable',
    holderBound: 'Portal session actor and server-selected subject',
    credential: 'No credential or Evidence assertion returned'
  };
}

function unavailableCrypto(scenario: ScenarioResult): NonNullable<ProofTrace['proof']> {
  return {
    signedBy: `No Evidence assertion; ${authorityLabel(scenario)} was unavailable`,
    algorithm: 'No response proof available',
    issuerKey: 'Not applicable',
    holderBound: 'The BFF selected the purpose and subject',
    credential: 'No credential or Evidence assertion returned'
  };
}

export class MockEvidenceProvider implements EvidenceProvider {
  #seq = 0;

  // The shared-seam method. The BFF calls this; it returns only the ClaimResult.
  // The richer evaluation (raw wire + proof material) is available via
  // evaluateDetailed for the tee-to-feed path.
  async evaluate(field: Field, ctx: EvaluateContext, opts?: EvaluateOptions): Promise<ClaimResult> {
    const { result } = await this.evaluateDetailed(field, ctx, opts);
    return result;
  }

  // Full evaluation used by the BFF: resolves the scenario, enforces the delegated
  // gate and the denial (no source read), builds the wire bodies, applies the
  // deterministic latency, and returns everything the BFF needs to tee a redacted
  // trace.
  async evaluateDetailed(
    field: Field,
    ctx: EvaluateContext,
    opts?: EvaluateOptions
  ): Promise<MockEvaluation> {
    const key = resolveScenarioKey(field, opts);
    const scenario = SCENARIOS[key];

    // Delegated source reads are only authorized AFTER the caregiver-link
    // verify succeeds. An unproven link is denied
    // before any dependent source read, proving the relationship-first gate.
    if (scenario.delegated && opts?.guardianLinkVerified !== true) {
      // Deny by default: a delegated dependent read is authorized ONLY with an
      // affirmative proven guardian link. An absent flag is treated as "not proven",
      // so the gate cannot be bypassed by omitting the flag on a raw API call.
      return this.#denied(field, scenario, ctx, key, 'relationship_not_proven');
    }

    const subject = resolveSubject(scenario, ctx, key);
    const seq = ++this.#seq;
    const evaluationId = makeOperationId(seq);
    const issuedAt =
      scenario.state === 'stale'
        ? new Date(`${scenario.asOf}T00:00:00.000Z`)
        : new Date();
    const plan = scenario.service === 'childBenefit' ? [] : authorityPlan(key, scenario);
    const applicationOwned = isApplicationOwnedPlan(plan);

    // Deterministic latency: honour the per-scenario delay so the UI can show the
    // top-to-bottom stagger and the SLOW threshold. We do not actually block the
    // event loop here beyond a short awaitable so tests stay fast; the BFF reads
    // timing.latencyMs to drive the animation budget.
    await delay(Math.min(scenario.latencyMs, 5));

    const applicationExchange = applicationOwned
      ? buildApplicationExchange(scenario, plan, subject, evaluationId, issuedAt)
      : undefined;
    const rawRequest =
      applicationExchange?.request ?? buildProviderRequest(scenario, subject);

    // Denial / error scenarios perform NO source read: there is no 200 body.
    if (scenario.httpStatus === 403) {
      return this.#denied(field, scenario, ctx, key, scenario.denial?.code ?? 'not_authorized');
    }
    if (scenario.httpStatus === 503) {
      return this.#errored(field, scenario, ctx, key, rawRequest);
    }

    const rawResponse = applicationExchange?.response ?? buildRawResponse(scenario, evaluationId, issuedAt);

    const result: ClaimResult = {
      state: scenario.state,
      display: scenario.display,
      ...(!applicationOwned ? { authority: scenario.authority } : {}),
      asOf: scenario.asOf,
      ...(scenario.reasonCode ? { reasonCode: scenario.reasonCode } : {}),
      traceId: `event ${seq}`
    };

    return {
      result,
      raw: {
        request: {
          method: applicationOwned ? 'MULTI' : 'POST',
          url: applicationOwned
            ? 'solmara://citizen-portal/application-composition'
            : evidenceUrl(scenario),
          body: rawRequest
        },
        response: { status: scenario.httpStatus, body: rawResponse }
      },
      proof: {
        headline: scenario.headline,
        answered: scenario.answered,
        notDisclosed: scenario.notDisclosed,
        status: scenario.status,
        authority: applicationOwned ? undefined : scenario.authority,
        purpose: scenario.purpose,
        presentations: applicationOwned
          ? plan.map((entry) => evidencePresentation(entry.authorityId, entry.source))
          : [evidencePresentation(scenario.authority, sourceForScenario(scenario))],
        crypto: buildCrypto(scenario, evaluationId, plan)
      },
      timing: {
        latencyMs: scenario.latencyMs,
        staggerOrder: scenario.staggerOrder,
        slow: scenario.latencyMs >= SLOW_THRESHOLD_MS
      }
    };
  }

  // A denied evaluation: 403, no source read, no 200 body. The boundary held.
  #denied(
    field: Field,
    scenario: ScenarioResult,
    _ctx: EvaluateContext,
    _key: string,
    code: string
  ): MockEvaluation {
    const seq = ++this.#seq;
    const evaluationId = makeOperationId(seq);
    // We still show the REQUEST the BFF attempted, with the stranger target, so the
    // inspector shows what was asked, then the 403 with no source read. The target
    // is redacted before it ever reaches the feed.
    const subject = scenario.denial ? PERSONA.karim : (scenario.subjectPersona ? PERSONA[scenario.subjectPersona] : PERSONA.mateo);
    const rawRequest = buildProviderRequest(scenario, subject);
    const denialBody: DenialBody = {
      type: `urn:solmara:portal:problem:${code}`,
      title: 'Portal authorization denied the request',
      status: 403,
      detail: scenario.denial?.message ?? 'requester is not authorized for this target',
      operation: evaluationId
    };
    const result: ClaimResult = {
      state: 'error',
      display:
        code === 'relationship_not_proven'
          ? 'Denied: guardian link not proven, no dependent record was read'
          : scenario.display,
      reasonCode: code,
      traceId: `event ${seq}`
    };
    return {
      result,
      raw: {
        request: {
          method: 'POST',
          url: 'solmara://citizen-portal/blocked-before-authority-call',
          body: rawRequest
        },
        response: { status: 403, body: denialBody }
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
        purpose: scenario.purpose,
        presentations: [],
        crypto: blockedCrypto(evaluationId)
      },
      timing: {
        latencyMs: scenario.latencyMs,
        staggerOrder: scenario.staggerOrder,
        slow: false
      }
    };
  }

  // A hard upstream failure (503): scoped to the field, framed as minimization. No
  // source read, no value.
  #errored(
    field: Field,
    scenario: ScenarioResult,
    _ctx: EvaluateContext,
    _key: string,
    rawRequest: RawProviderRequest
  ): MockEvaluation {
    const seq = this.#seq; // already incremented by the caller
    const errBody: DenialBody = {
      type: 'https://registrystack.org/problems/evidence/service_unavailable',
      title: 'Authority Evidence is unavailable',
      status: 503,
      detail: `could not reach ${authorityLabel(scenario)}`,
      operation: `unavailable:${seq}`
    };
    const result: ClaimResult = {
      state: 'error',
      display: scenario.display,
      authority: scenario.authority,
      reasonCode: scenario.reasonCode,
      traceId: `event ${seq}`
    };
    return {
      result,
      raw: {
        request: { method: 'POST', url: evidenceUrl(scenario), body: rawRequest },
        response: { status: 503, body: errBody }
      },
      proof: {
        headline: scenario.headline,
        answered: scenario.answered,
        notDisclosed: scenario.notDisclosed,
        status: 'error',
        authority: scenario.authority,
        purpose: scenario.purpose,
        presentations: [evidencePresentation(scenario.authority, sourceForScenario(scenario))],
        crypto: unavailableCrypto(scenario)
      },
      timing: {
        latencyMs: scenario.latencyMs,
        staggerOrder: scenario.staggerOrder,
        slow: scenario.latencyMs >= SLOW_THRESHOLD_MS
      }
    };
  }
}

function buildApplicationExchange(
  scenario: ScenarioResult,
  plan: AuthorityPlan[],
  subject: string,
  evaluationId: string,
  issuedAt: Date
): { request: RawApplicationRequest; response: RawApplicationResponse } {
  const purposes = [...new Set(plan.map((authority) => authority.purpose))];
  const request: RawApplicationRequest = {
    purpose:
      purposes.length === 1
        ? (purposes[0] ?? '')
        : 'application-composed-from-source-authorized-purposes',
    composition: 'portal-application',
    requests: plan.map((authority, index) => ({
      authority: authority.authority,
      service_id: authority.serviceId,
      body: buildEvidenceRequest(
        authority.claimId,
        subject,
        authority.purpose,
        authority.scheme ?? 'solmara_uin',
        index + 1
      )
    }))
  };
  return {
    request,
    response: {
      schema_version: 'solmara-portal-evidence/v1',
      orchestration: {
        service_id: 'citizen-portal',
        decision: 'application_composed'
      },
      signed_evidence: plan.map((authority, index) => ({
        authority: authority.authority,
        service_id: authority.serviceId,
        assertion: signEvidence(
          buildEvidenceAssertion(
            scenario,
            `${evaluationId}-${index + 1}`,
            issuedAt,
            authority.claimId,
            authority.serviceId,
            true,
            authority.authorityId
          ),
          authority.serviceId
        )
      })),
      source_trace: plan.map((authority) => ({
        authority: authority.authority,
        service_id: authority.serviceId,
        status: 200,
        requirements: [`urn:solmara:requirement:${authority.claimId}:v1`]
      })),
      derived_decisions: { [scenario.claimId]: scenario.satisfied }
    }
  };
}

function buildProviderRequest(
  scenario: ScenarioResult,
  subject: string
): RawProviderRequest {
  return buildRawRequest(scenario, subject);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sourceForScenario(scenario: ScenarioResult): EvidenceSource {
  if (
    scenario.service === 'childBenefit' &&
    ['childCivil', 'population', 'socialRegistry'].includes(scenario.authority)
  ) {
    return 'immutable extract';
  }
  return 'Relay lookup';
}

export type { ProofStatus };

// Re-export the canned scenario keys so the BFF / state gallery can enumerate the
// reachable states without importing the table directly.
export { PERSONA, SCENARIOS } from './scenarios';
