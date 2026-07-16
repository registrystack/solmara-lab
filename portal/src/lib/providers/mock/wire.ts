// Wire-shape builders. Registry Notary services use EvaluateRequest and
// EvaluationResponse. Child benefit uses an ordinary application-owned JSON
// request and source-attributed evidence response.
//
// Volatile fields (evaluation_id, issued_at, expires_at) are stamped here from
// the passed clock/ids so they are present but value-variable. The live provider
// will emit the same shape; only the values differ.

import type { ScenarioResult } from './scenarios';
import {
  AUTHORITY_LABEL,
  NOTARY_SERVICE_ID
} from './scenarios';

// A monotonic, demo-stable ULID-shaped id. Not a real ULID; deterministic so the
// mock is reproducible while still looking like the wire format.
export function makeEvaluationId(seed: number): string {
  const base = '01HX7Y5F2WAJ7ZP0Q4M5K9E8N';
  const tail = (seed % 36).toString(36).toUpperCase();
  return `${base}${tail}`;
}

// The full target/subject value the BFF holds server-side. This is the RAW shape
// the BFF builds and would send upstream; it is redacted before it ever reaches
// the proof feed. We expose it so the redaction test can prove the raw subject
// never appears in the streamed output.
export type RawEvaluateRequest = {
  claims: string[];
  purpose: string;
  disclosure: string;
  format: string;
  relationship: { type: string };
  target: { type: string; identifiers: { scheme: string; value: string }[] };
  on_behalf_of?: { actor: { type: string; id_hash: string }; delegation_ref: string };
};

export const CLAIM_RESULT_FORMAT = 'application/vnd.registry-notary.claim-result+json';
export const CHILD_BENEFIT_FORMAT = 'application/json';

export type RawChildBenefitRequest = {
  target: { type: 'Person'; identifiers: { scheme: 'solmara_uin'; value: string }[] };
  claims: string[];
  disclosure: 'predicate';
  format: typeof CHILD_BENEFIT_FORMAT;
  variables?: { as_of_date: string };
  purpose?: never;
  relationship?: never;
  on_behalf_of?: never;
};

export type RawApplicationRequest = {
  purpose: string;
  disclosure: 'decision';
  composition: 'application';
  requests: {
    authority: string;
    service_id: string;
    body: RawEvaluateRequest;
  }[];
};

export type RawProviderRequest =
  | RawEvaluateRequest
  | RawChildBenefitRequest
  | RawApplicationRequest;

export function buildChildBenefitRequest(
  scenario: ScenarioResult,
  subject: string
): RawChildBenefitRequest {
  return {
    target: {
      type: 'Person',
      identifiers: [{ scheme: 'solmara_uin', value: subject }]
    },
    claims: [scenario.claimId],
    disclosure: 'predicate',
    format: CHILD_BENEFIT_FORMAT,
    ...(scenario.claimId === 'child-age-under-5'
      ? { variables: { as_of_date: scenario.asOf } }
      : {})
  };
}

export function buildEvaluationRequest(
  claimId: string,
  subject: string,
  purpose: string,
  scheme = 'solmara_uin'
): RawEvaluateRequest {
  return {
    claims: [claimId],
    purpose,
    disclosure: 'predicate',
    format: CLAIM_RESULT_FORMAT,
    relationship: { type: 'self' },
    target: {
      type: 'Person',
      identifiers: [{ scheme, value: subject }]
    }
  };
}

// Build the RAW EvaluateRequest the BFF would send. `subject` is the national id
// the BFF resolved server-side (never client-supplied). For delegated reads the
// subject is the dependent and actorIdHash binds the requesting guardian.
export function buildRawRequest(
  scenario: ScenarioResult,
  subject: string,
  opts?: { actorIdHash?: string; delegationRef?: string }
): RawEvaluateRequest {
  const req = buildEvaluationRequest(
    scenario.claimId,
    subject,
    scenario.purpose,
    subjectScheme(scenario)
  );
  req.disclosure = scenario.disclosure;
  req.relationship = { type: scenario.delegated ? 'guardian' : 'self' };
  if (scenario.delegated) {
    req.on_behalf_of = {
      actor: {
        type: 'Person',
        // Already a keyed hash placeholder; the redactor still re-hashes any raw
        // id, but the wire shape carries id_hash, never a raw principal.
        id_hash: opts?.actorIdHash ?? 'hmac-sha256:0000'
      },
      delegation_ref: opts?.delegationRef ?? 'rnref:v1:caregiver-link'
    };
  }
  return req;
}

// One ClaimResultView, structurally identical to the OpenAPI required key set and
// ordering. Volatile fields stamped from `clock`/`evaluationId`.
export type ClaimResultView = {
  claim_id: string;
  claim_version: string;
  disclosure: string;
  evaluation_id: string;
  expires_at: string | null;
  format: string;
  issued_at: string;
  provenance: {
    derived_from: object[];
    generated_by: {
      claim_id: string;
      claim_version: string;
      evaluation_id: string;
      policy_hash?: string;
      policy_id?: string;
      policy_version?: string;
      service_id: string;
      type: 'claim_evaluation';
    };
    schema_version: 'registry-notary-claim-provenance/v2';
    used: {
      relay_consultation_count: number;
    };
  };
  satisfied: boolean | null;
  subject_type: string;
  target_ref: {
    handle: string;
    identifier_schemes?: string[];
    profile?: string;
    type?: string;
  };
  value: unknown;
};

export type RawEvaluationResponse = { results: ClaimResultView[] };

export type ChildBenefitResult = {
  claim_id: string;
  claim_version: string;
  format: string;
  issued_at: string;
  expires_at: string | null;
  notary_service_id: string;
  authority: string;
  satisfied: boolean;
  disclosure: 'predicate';
};

export type RawChildBenefitResponse = {
  schema_version: 'solmara-child-benefit-evidence/v1';
  evidence_set_id: string;
  orchestration: {
    service_id: 'child-benefit-federator';
    decision: 'not_composed';
  };
  purpose: string;
  target: { type?: string; identifier_schemes: string[] };
  results: ChildBenefitResult[];
  source_trace: object[];
};

export type RawApplicationResponse = {
  schema_version: 'solmara-portal-evidence/v1';
  orchestration: {
    service_id: 'citizen-portal';
    decision: 'application_composed';
  };
  results: ClaimResultView[];
  source_trace: {
    authority: string;
    service_id: string;
    status: number;
    claims: string[];
  }[];
  derived_decisions?: Record<string, boolean | null>;
};

export type RawProviderResponse =
  | RawEvaluationResponse
  | RawChildBenefitResponse
  | RawApplicationResponse;

export type ClaimResultFixture = {
  claimId: string;
  claimVersion: string;
  serviceId: string;
  subjectType: string;
  satisfied: boolean | null;
  value: unknown;
  disclosure: string;
  sourceCount: number;
  identifierScheme: string;
  freshnessDays: number;
};

export function buildChildBenefitResponse(
  scenario: ScenarioResult,
  evaluationId: string,
  issuedAt: Date,
  target: RawChildBenefitRequest['target']
): RawChildBenefitResponse {
  const serviceId = NOTARY_SERVICE_ID[scenario.notary];
  return {
    schema_version: 'solmara-child-benefit-evidence/v1',
    evidence_set_id: `cbe_${evaluationId}`,
    orchestration: {
      service_id: 'child-benefit-federator',
      decision: 'not_composed'
    },
    purpose: scenario.purpose,
    target: {
      type: target.type,
      identifier_schemes: target.identifiers.map((identifier) => identifier.scheme)
    },
    results: [
      {
        claim_id: scenario.claimId,
        claim_version: scenario.claimVersion,
        format: CLAIM_RESULT_FORMAT,
        issued_at: issuedAt.toISOString(),
        expires_at: new Date(
          issuedAt.getTime() + scenario.freshnessDays * 24 * 60 * 60 * 1000
        ).toISOString(),
        notary_service_id: serviceId,
        authority: AUTHORITY_LABEL[scenario.notary],
        satisfied: scenario.satisfied === true,
        disclosure: 'predicate'
      }
    ],
    source_trace: [
      {
        authority: AUTHORITY_LABEL[scenario.notary],
        service_id: serviceId,
        claims: [scenario.claimId]
      }
    ]
  };
}

// Build the RAW 200 EvaluationResponse. issuedAt is an ISO string; expiresAt is
// issuedAt + freshnessDays (can be in the past for the stale scenario).
export function buildRawResponse(
  scenario: ScenarioResult,
  evaluationId: string,
  issuedAt: Date
): RawEvaluationResponse {
  return {
    results: [
      buildClaimResultView(
        {
          claimId: scenario.claimId,
          claimVersion: scenario.claimVersion,
          serviceId: NOTARY_SERVICE_ID[scenario.notary],
          subjectType: scenario.subjectType,
          satisfied: scenario.satisfied,
          value: scenario.value,
          disclosure: scenario.disclosure,
          sourceCount: scenario.sourceCount,
          identifierScheme: subjectScheme(scenario),
          freshnessDays: scenario.freshnessDays
        },
        evaluationId,
        issuedAt
      )
    ]
  };
}

export function buildClaimResultView(
  fixture: ClaimResultFixture,
  evaluationId: string,
  issuedAt: Date
): ClaimResultView {
  const issued = issuedAt.toISOString();
  const expires = new Date(
    issuedAt.getTime() + fixture.freshnessDays * 24 * 60 * 60 * 1000
  ).toISOString();
  return {
    claim_id: fixture.claimId,
    claim_version: fixture.claimVersion,
    disclosure: fixture.disclosure,
    evaluation_id: evaluationId,
    expires_at: expires,
    format: CLAIM_RESULT_FORMAT,
    issued_at: issued,
    provenance: {
      derived_from: [],
      generated_by: {
        claim_id: fixture.claimId,
        claim_version: fixture.claimVersion,
        evaluation_id: evaluationId,
        service_id: fixture.serviceId,
        type: 'claim_evaluation'
      },
      schema_version: 'registry-notary-claim-provenance/v2',
      used: {
        relay_consultation_count: fixture.sourceCount
      }
    },
    satisfied: fixture.satisfied,
    subject_type: fixture.subjectType,
    target_ref: {
      handle: 'rnref:v1:target',
      identifier_schemes: [fixture.identifierScheme],
      profile: 'resident',
      type: 'Person'
    },
    value: fixture.value
  };
}

// The HTTP method + URL the proof inspector shows. URL carries the notary host
// but never a raw subject (subjects go in the body target, which is redacted).
export function notaryUrl(scenario: ScenarioResult): string {
  if (scenario.service === 'childBenefit') {
    return 'https://child-benefit-federator.solmara.registrystack.org/v1/evaluations';
  }
  return `https://${NOTARY_SERVICE_ID[scenario.notary]}.solmara.registrystack.org/v1/evaluations`;
}

// The authority label the result attributes to (depth-1 answered line).
export function authorityLabel(scenario: ScenarioResult): string {
  return AUTHORITY_LABEL[scenario.notary];
}

function subjectScheme(scenario: ScenarioResult): string {
  return scenario.notary === 'agri' ? 'farmer_id' : 'solmara_uin';
}
