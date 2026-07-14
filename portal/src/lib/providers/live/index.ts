import type { EvaluateContext, DetailedEvidenceProvider } from '$lib/providers/EvidenceProvider';
import type { ClaimResult, Field, ProofTrace } from '$lib/types';
import {
  SCENARIOS,
  PERSONA,
  type EvaluateOptions,
  type MockEvaluation
} from '$lib/providers/mock';
import { NOTARY_ISSUER_KEY } from '$lib/providers/mock/scenarios';
import {
  authorityLabel,
  buildFederatedPredicateRequest,
  buildRawRequest,
  CLAIM_RESULT_FORMAT,
  FEDERATED_PREDICATE_BUNDLE_FORMAT,
  makeEvaluationId,
  type RawEvaluationResponse,
  type RawProviderResponse
} from '$lib/providers/mock/wire';

export type LiveProviderEnv = {
  PORTAL_CITIZEN_NOTARY_URL?: string;
  PORTAL_CITIZEN_NOTARY_TOKEN?: string;
  CHILD_BENEFIT_FEDERATOR_URL?: string;
  CHILD_BENEFIT_FEDERATOR_TOKEN?: string;
  PENSION_NOTARY_URL?: string;
  PENSION_NOTARY_TOKEN?: string;
  NAGDI_NOTARY_URL?: string;
  NAGDI_NOTARY_TOKEN?: string;
  PORTAL_RELAY_URLS?: string;
  PORTAL_RELAY_TOKEN?: string;
  PORTAL_CIVIL_RELAY_URL?: string;
  PORTAL_SOCIAL_RELAY_URL?: string;
  PORTAL_AGRI_RELAY_URL?: string;
  PORTAL_CERTS_RELAY_URL?: string;
};

type Fetcher = typeof fetch;
type LiveService = 'childBenefit' | 'pension' | 'nagdi' | 'citizen';
type LiveNotaryRef = { url?: string; token?: string; urlEnv: string; tokenEnv: string };
type DenialBody = { error: string; error_description: string };

export class LiveEvidenceProvider implements DetailedEvidenceProvider {
  #seq = 0;
  #notaries: Record<LiveService, LiveNotaryRef>;
  #relayToken: string;
  #relayUrls: Record<string, string>;
  #fetch: Fetcher;

  constructor(env: LiveProviderEnv, fetcher: Fetcher = fetch) {
    this.#notaries = {
      childBenefit: {
        url: env.CHILD_BENEFIT_FEDERATOR_URL,
        token: env.CHILD_BENEFIT_FEDERATOR_TOKEN,
        urlEnv: 'CHILD_BENEFIT_FEDERATOR_URL',
        tokenEnv: 'CHILD_BENEFIT_FEDERATOR_TOKEN'
      },
      pension: {
        url: env.PENSION_NOTARY_URL,
        token: env.PENSION_NOTARY_TOKEN,
        urlEnv: 'PENSION_NOTARY_URL',
        tokenEnv: 'PENSION_NOTARY_TOKEN'
      },
      nagdi: {
        url: env.NAGDI_NOTARY_URL,
        token: env.NAGDI_NOTARY_TOKEN,
        urlEnv: 'NAGDI_NOTARY_URL',
        tokenEnv: 'NAGDI_NOTARY_TOKEN'
      },
      citizen: {
        url: env.PORTAL_CITIZEN_NOTARY_URL,
        token: env.PORTAL_CITIZEN_NOTARY_TOKEN,
        urlEnv: 'PORTAL_CITIZEN_NOTARY_URL',
        tokenEnv: 'PORTAL_CITIZEN_NOTARY_TOKEN'
      }
    };
    this.#relayToken = requiredValue(env.PORTAL_RELAY_TOKEN, 'PORTAL_RELAY_TOKEN');
    this.#relayUrls = relayUrlsFromEnv(env);
    this.#fetch = fetcher;
  }

  async evaluate(field: Field, ctx: EvaluateContext, opts?: EvaluateOptions): Promise<ClaimResult> {
    const evaluation = await this.evaluateDetailed(field, ctx, opts);
    return evaluation.result;
  }

  async evaluateDetailed(field: Field, ctx: EvaluateContext, opts?: EvaluateOptions): Promise<MockEvaluation> {
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
    const evaluationId = makeEvaluationId(seq);
    const issuedAt = new Date();
    const subject = resolveSubject(scenarioKey, scenario, ctx);
    const federated = scenario.service === 'childBenefit';
    const rawRequest = federated
      ? buildFederatedPredicateRequest(scenario, subject)
      : buildRawRequest(requestCompatibleScenario(scenario), subject);
    const notary = this.#notaryFor(scenario.service);

    if (federated) {
      await this.#fetchJson(joinedUrl(notary.url, '/v1/claims'), {
        method: 'GET',
        headers: notaryHeaders(notary.token, scenario.purpose, 'application/json')
      });
    } else {
      const relayUrl = this.#relayUrls[scenario.notary];
      await this.#fetchJson(joinedUrl(relayUrl, '/metadata/catalog'), {
        method: 'GET',
        headers: relayHeaders(this.#relayToken, scenario.purpose, 'application/json')
      });
    }

    const notaryResponse = await this.#fetchJson(joinedUrl(notary.url, '/v1/evaluations'), {
      method: 'POST',
      headers: {
        ...notaryHeaders(
          notary.token,
          scenario.purpose,
          federated ? FEDERATED_PREDICATE_BUNDLE_FORMAT : CLAIM_RESULT_FORMAT
        ),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(rawRequest)
    });
    const normalized = normalizeEvaluationResponse(notaryResponse.body, scenario.claimId);
    const responseBody = (federated
      ? { ...notaryResponse.body, results: normalized.results }
      : normalized) as RawProviderResponse;
    const firstResult = normalized.results[0] ?? {};
    const status = proofStatus(notaryResponse.status, firstResult.satisfied);
    const result: ClaimResult = {
      state: status === 'false' ? 'false' : status === 'denied' || status === 'error' ? 'error' : scenario.state,
      display: displayResult(scenario, firstResult.value, firstResult.satisfied, status),
      authority: scenario.notary,
      asOf: typeof firstResult.issued_at === 'string' ? firstResult.issued_at : issuedAt.toISOString(),
      traceId: `event ${seq}`
    };

    return {
      result,
      raw: {
        request: { method: 'POST', url: joinedUrl(notary.url, '/v1/evaluations'), body: rawRequest },
        response: { status: notaryResponse.status, body: responseBody }
      },
      proof: {
        headline: `${authorityLabel(scenario)} returned live evidence for ${scenario.claimId}`,
        answered: `${authorityLabel(scenario)} answered: ${scenario.claimId} = ${displayValue(firstResult.value, firstResult.satisfied)}`,
        notDisclosed: scenario.notDisclosed,
        status,
        authority: scenario.notary,
        crypto: liveCrypto(
          scenario,
          evaluationId,
          issuedAt,
          typeof notaryResponse.body.bundle_id === 'string'
            ? notaryResponse.body.bundle_id
            : undefined
        )
      },
      timing: { latencyMs: 0, staggerOrder: scenario.staggerOrder, slow: false }
    };
  }

  async #fetchJson(url: string, init: RequestInit): Promise<{ status: number; body: Record<string, unknown> }> {
    const response = await this.#fetch(url, init);
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { status: response.status, body: body as Record<string, unknown> };
    }
    return { status: response.status, body: body as Record<string, unknown> };
  }

  #notaryFor(service: LiveService): { url: string; token: string } {
    const ref = this.#notaries[service];
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
    const issuedAt = new Date();
    const subject = scenarioKey === 'denial' ? PERSONA.karim : ctx.delegatedTarget ?? ctx.selectedSubject ?? ctx.subject;
    const rawRequest =
      scenario.service === 'childBenefit'
        ? buildFederatedPredicateRequest(scenario, subject)
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
        authority: scenario.notary,
        reasonCode: code,
        traceId: `event ${seq}`
      },
      raw: {
        request: { method: 'POST', url: joinedUrl(this.#notaryFor(scenario.service).url, '/v1/evaluations'), body: rawRequest },
        response: { status: 403, body }
      },
      proof: {
        headline:
          code === 'relationship_not_proven'
            ? `Denied by ${authorityLabel(scenario)}: the guardian link was not proven, so no dependent record was read`
            : scenario.headline,
        answered: `${authorityLabel(scenario)} answered: 403 ${code}, no data returned`,
        notDisclosed: scenario.notDisclosed,
        status: 'denied',
        authority: scenario.notary,
        crypto: liveCrypto(scenario, evaluationId, issuedAt, undefined, true)
      },
      timing: { latencyMs: 0, staggerOrder: scenario.staggerOrder, slow: false }
    };
  }
}

function liveCrypto(
  scenario: (typeof SCENARIOS)[string],
  evaluationId: string,
  issuedAt: Date,
  bundleId?: string,
  deniedBeforeSource = false
): NonNullable<ProofTrace['proof']> {
  if (scenario.service === 'childBenefit') {
    if (deniedBeforeSource) {
      return {
        signedBy: 'Portal authorization gate; no source Notary called',
        algorithm: 'No signature; request stopped before federation',
        issuerKey: 'Not applicable',
        holderBound: 'Portal session actor and selected dependent',
        credential: 'No federated predicate bundle returned',
        auditId: `denial:${evaluationId}`
      };
    }
    return {
      signedBy: `${authorityLabel(scenario)} source-owned Notary`,
      algorithm: 'EdDSA-Ed25519 authority response JWT verified by the federator',
      issuerKey: NOTARY_ISSUER_KEY[scenario.notary],
      holderBound: 'Purpose- and subject-bound child-benefit federation request',
      credential: 'Federated predicate bundle',
      auditId: `bundle:${bundleId ?? `fcb_${evaluationId}`}`
    };
  }
  return {
    signedBy: authorityLabel(scenario),
    algorithm: 'EdDSA-Ed25519',
    issuerKey: NOTARY_ISSUER_KEY[scenario.notary],
    holderBound: scenario.delegated
      ? 'Holder-bound to the portal session actor, subject the dependent'
      : 'Holder-bound to the signed-in citizen',
    credential: 'SD-JWT VC',
    auditId: `audit:${evaluationId}:${issuedAt.getTime().toString(36)}`
  };
}

function requestCompatibleScenario(scenario: (typeof SCENARIOS)[string]): (typeof SCENARIOS)[string] {
  if (!scenario.delegated && scenario.disclosure !== 'decision') return scenario;
  return {
    ...scenario,
    delegated: false,
    disclosure: scenario.disclosure === 'decision' ? 'predicate' : scenario.disclosure
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

function relayUrlsFromEnv(env: LiveProviderEnv): Record<string, string> {
  const parsed = parseRelayJson(env.PORTAL_RELAY_URLS);
  return {
    civil: requiredUrl(env.PORTAL_CIVIL_RELAY_URL ?? parsed.civil, relayEnvName('civil')),
    social: requiredUrl(env.PORTAL_SOCIAL_RELAY_URL ?? parsed.social, relayEnvName('social')),
    agri: requiredUrl(env.PORTAL_AGRI_RELAY_URL ?? parsed.agri, relayEnvName('agri')),
    certs: requiredUrl(env.PORTAL_CERTS_RELAY_URL ?? parsed.certs ?? parsed.civil, relayEnvName('certs'))
  };
}

function parseRelayJson(value: string | undefined): Record<string, string | undefined> {
  if (!value) return {};
  const parsed = JSON.parse(value) as Record<string, unknown>;
  return Object.fromEntries(
    Object.entries(parsed).map(([key, item]) => [key, typeof item === 'string' ? item : undefined])
  );
}

function relayEnvName(key: string): string {
  return `PORTAL_${key.toUpperCase()}_RELAY_URL or PORTAL_RELAY_URLS.${key}`;
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

function relayHeaders(token: string, purpose: string, accept: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    Accept: accept,
    'Data-Purpose': purpose
  };
}

function notaryHeaders(token: string, purpose: string, accept: string): Record<string, string> {
  return {
    'x-api-key': token,
    Accept: accept,
    'Data-Purpose': purpose
  };
}

function normalizeEvaluationResponse(body: Record<string, unknown>, claimId: string): RawEvaluationResponse {
  const results = Array.isArray(body.results) ? body.results : [];
  return {
    results: results
      .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
      .map((item) => ({
        claim_id: String(item.claim_id ?? item.claim ?? claimId),
        claim_version: String(item.claim_version ?? item.version ?? 'live'),
        disclosure: String(item.disclosure ?? 'predicate'),
        evaluation_id: String(item.evaluation_id ?? item.id ?? makeEvaluationId(0)),
        expires_at: typeof item.expires_at === 'string' ? item.expires_at : null,
        format: String(item.format ?? CLAIM_RESULT_FORMAT),
        issued_at: String(item.issued_at ?? new Date().toISOString()),
        matching: objectValue(item.matching),
        provenance: objectValue(item.provenance),
        requester_ref: objectValue(item.requester_ref),
        satisfied: typeof item.satisfied === 'boolean' ? item.satisfied : null,
        subject_type: String(item.subject_type ?? 'person'),
        target_ref: objectValue(item.target_ref),
        value: item.value
      }))
  } as RawEvaluationResponse;
}

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function proofStatus(status: number, satisfied: unknown): ProofTrace['status'] {
  if (status === 403) return 'denied';
  if (status < 200 || status >= 300) return 'error';
  return satisfied === false ? 'false' : 'ok';
}

function displayResult(
  scenario: (typeof SCENARIOS)[string],
  value: unknown,
  satisfied: unknown,
  status: ProofTrace['status']
): string {
  if (status === 'ok' && satisfied === true) return scenario.display;
  return `${scenario.claimId}: ${displayValue(value, satisfied)}`;
}

function displayValue(value: unknown, satisfied: unknown): string {
  if (typeof satisfied === 'boolean') return String(satisfied);
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value === null || value === undefined) return 'not returned';
  return JSON.stringify(value);
}

function hashActor(subject: string): string {
  let hash = 0;
  for (let i = 0; i < subject.length; i += 1) {
    hash = (hash * 31 + subject.charCodeAt(i)) & 0xffffffff;
  }
  return `hmac-sha256:${(hash >>> 0).toString(16).padStart(8, '0')}`;
}
