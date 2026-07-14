// Wire-shape builders. Registry Notary services use EvaluateRequest and
// EvaluationResponse. Child benefit uses the federated predicate bundle
// request and response contract.
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
  claims: { id: string; version: string }[];
  purpose: string;
  disclosure: string;
  format: string;
  relationship: { type: string };
  target: { type: string; identifiers: { scheme: string; value: string }[] };
  on_behalf_of?: { actor: { type: string; id_hash: string }; delegation_ref: string };
};

export const CLAIM_RESULT_FORMAT = 'application/vnd.registry-notary.claim-result+json';
export const FEDERATED_PREDICATE_BUNDLE_FORMAT =
  'application/vnd.solmara.federated-predicate-bundle+json';

export type RawFederatedPredicateRequest = {
  target: { type: 'Person'; identifiers: { scheme: 'solmara_uin'; value: string }[] };
  claims: string[];
  disclosure: 'predicate';
  format: typeof FEDERATED_PREDICATE_BUNDLE_FORMAT;
  purpose?: never;
  relationship?: never;
  on_behalf_of?: never;
};

export type RawProviderRequest = RawEvaluateRequest | RawFederatedPredicateRequest;

export function buildFederatedPredicateRequest(
  scenario: ScenarioResult,
  subject: string
): RawFederatedPredicateRequest {
  return {
    target: {
      type: 'Person',
      identifiers: [{ scheme: 'solmara_uin', value: subject }]
    },
    claims: [scenario.claimId],
    disclosure: 'predicate',
    format: FEDERATED_PREDICATE_BUNDLE_FORMAT
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
  const req: RawEvaluateRequest = {
    claims: [{ id: scenario.claimId, version: scenario.claimVersion }],
    purpose: scenario.purpose,
    disclosure: scenario.disclosure,
    format: CLAIM_RESULT_FORMAT,
    relationship: { type: scenario.delegated ? 'guardian' : 'self' },
    target: {
      type: 'Person',
      identifiers: [{ scheme: subjectScheme(scenario), value: subject }]
    }
  };
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
  matching: {
    confidence: string;
    method: string;
    policy_id: string;
    score: number | null;
  };
  provenance: {
    derived_from: object[];
    generated_by: {
      claim_id: string;
      claim_version: string;
      evaluation_id: string;
      policy_hash: string;
      policy_id: string;
      policy_version: string;
      service_id: string;
      type: 'claim_evaluation';
    };
    schema_version: 'registry-notary-claim-provenance/v1';
    used: {
      source_count: number;
      source_runtimes: object[];
      source_versions: Record<string, string>;
    };
  };
  requester_ref: {
    handle: string;
    identifier_schemes: string[];
    profile: string;
    type: string;
  };
  satisfied: boolean | null;
  subject_type: string;
  target_ref: {
    handle: string;
    identifier_schemes: string[];
    profile: string;
    type: string;
  };
  value: unknown;
};

export type RawEvaluationResponse = { results: ClaimResultView[] };

export type FederatedPredicateResult = {
  claim_id: string;
  claim_version: string;
  format: string;
  issued_at: string;
  notary_service_id: string;
  authority: string;
  federation_profile: string;
  satisfied: boolean;
  value: boolean;
  disclosure: 'predicate';
  federation: {
    issuer: string;
    subject: string;
    request_jti: string;
    profile: string;
  };
};

export type RawFederatedPredicateResponse = {
  schema_version: 'solmara-child-benefit-federator/v1';
  bundle_id: string;
  federator: {
    service_id: 'child-benefit-federator';
    issuer: 'https://child-benefit-federator.solmara.registrystack.org';
    decision: 'not_composed';
  };
  purpose: string;
  target: RawFederatedPredicateRequest['target'];
  results: FederatedPredicateResult[];
  federation_trace: object[];
};

export type RawProviderResponse = RawEvaluationResponse | RawFederatedPredicateResponse;

export function buildFederatedPredicateResponse(
  scenario: ScenarioResult,
  evaluationId: string,
  issuedAt: Date,
  target: RawFederatedPredicateRequest['target']
): RawFederatedPredicateResponse {
  const serviceId = NOTARY_SERVICE_ID[scenario.notary];
  const authorityHost = serviceId;
  return {
    schema_version: 'solmara-child-benefit-federator/v1',
    bundle_id: `fcb_${evaluationId}`,
    federator: {
      service_id: 'child-benefit-federator',
      issuer: 'https://child-benefit-federator.solmara.registrystack.org',
      decision: 'not_composed'
    },
    purpose: scenario.purpose,
    target,
    results: [
      {
        claim_id: scenario.claimId,
        claim_version: scenario.claimVersion,
        format: CLAIM_RESULT_FORMAT,
        issued_at: issuedAt.toISOString(),
        notary_service_id: serviceId,
        authority: AUTHORITY_LABEL[scenario.notary],
        federation_profile: scenario.claimId.replaceAll('-', '_'),
        satisfied: scenario.satisfied === true,
        value: scenario.satisfied === true,
        disclosure: 'predicate',
        federation: {
          issuer: `https://${authorityHost}.solmara.registrystack.org`,
          subject: `did:web:${authorityHost}.solmara.registrystack.org`,
          request_jti: evaluationId,
          profile: scenario.claimId.replaceAll('-', '_')
        }
      }
    ],
    federation_trace: []
  };
}

// Build the RAW 200 EvaluationResponse. issuedAt is an ISO string; expiresAt is
// issuedAt + freshnessDays (can be in the past for the stale scenario).
export function buildRawResponse(
  scenario: ScenarioResult,
  evaluationId: string,
  issuedAt: Date
): RawEvaluationResponse {
  const issued = issuedAt.toISOString();
  const expires = new Date(
    issuedAt.getTime() + scenario.freshnessDays * 24 * 60 * 60 * 1000
  ).toISOString();
  const view: ClaimResultView = {
    claim_id: scenario.claimId,
    claim_version: scenario.claimVersion,
    disclosure: scenario.disclosure,
    evaluation_id: evaluationId,
    expires_at: expires,
    format: CLAIM_RESULT_FORMAT,
    issued_at: issued,
    matching: {
      confidence: scenario.sourceCount > 1 ? 'medium' : 'high',
      method: 'identifier_exact',
      policy_id: 'national-id-exact-v1',
      score: scenario.sourceCount === 1 ? 1.0 : null
    },
    provenance: {
      derived_from: [],
      generated_by: {
        claim_id: scenario.claimId,
        claim_version: scenario.claimVersion,
        evaluation_id: evaluationId,
        policy_hash:
          'sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08',
        policy_id: scenario.delegated ? 'delegated-attestation' : 'self-attestation',
        policy_version: 'v1',
        service_id: NOTARY_SERVICE_ID[scenario.notary],
        type: 'claim_evaluation'
      },
      schema_version: 'registry-notary-claim-provenance/v1',
      used: {
        source_count: scenario.sourceCount,
        source_runtimes: [],
        source_versions: {}
      }
    },
    requester_ref: {
      handle: 'rnref:v1:solmara-portal',
      identifier_schemes: ['agency_id'],
      profile: 'benefits',
      type: 'Agency'
    },
    satisfied: scenario.satisfied,
    subject_type: scenario.subjectType,
    target_ref: {
      handle: 'rnref:v1:target',
      identifier_schemes: [subjectScheme(scenario)],
      profile: 'resident',
      type: 'Person'
    },
    value: scenario.value
  };
  return { results: [view] };
}

// The HTTP method + URL the proof inspector shows. URL carries the notary host
// but never a raw subject (subjects go in the body target, which is redacted).
export function notaryUrl(scenario: ScenarioResult): string {
  if (scenario.service === 'childBenefit') {
    return 'https://child-benefit-federator.solmara.registrystack.org/v1/evaluations';
  }
  return `https://citizen-notary.solmara.registrystack.org/v1/evaluations`;
}

// The authority label the result attributes to (depth-1 answered line).
export function authorityLabel(scenario: ScenarioResult): string {
  return AUTHORITY_LABEL[scenario.notary];
}

function subjectScheme(scenario: ScenarioResult): string {
  return scenario.notary === 'agri' ? 'farmer_id' : 'solmara_uin';
}
