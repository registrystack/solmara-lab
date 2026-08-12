// Registry Evidence wire-shape builders used by the portal mock. The request
// matches EvidenceRequest v1 and the response is a signed flattened JWS. The
// portal treats the encoded assertion as opaque transport data and projects the
// reviewed concept into its stable ClaimResult UI model.

import type { ScenarioResult } from './scenarios';
import { AUTHORITY_LABEL, EVIDENCE_SERVICE_ID } from './scenarios';

const REQUEST_NONCE_BASE = 'U29sbWFyYVJlZ2lzdHJ5RXZpZGVuY2VEZW1vMDAwMDA';
const SIGNATURE = 'A'.repeat(86);

export const EVIDENCE_RESPONSE_FORMAT = 'application/jose+json';

export function makeOperationId(seed: number): string {
  const base = '01HX7Y5F2WAJ7ZP0Q4M5K9E8N';
  return `${base.slice(0, 25)}${(seed % 32).toString(32).toUpperCase()}`;
}

export type EvidenceSelector = {
  profile: string;
  values: Record<string, string>;
};

export type RawEvidenceRequest = {
  requestNonce: string;
  requirement: string;
  purpose: string;
  subjects: { role: string; selector: EvidenceSelector }[];
};

export type RawApplicationRequest = {
  purpose: string;
  composition: 'portal-application';
  requests: {
    authority: string;
    service_id: string;
    body: RawEvidenceRequest;
  }[];
};

export type RawProviderRequest = RawEvidenceRequest | RawApplicationRequest;

export type EvidenceAssertion = {
  schema: 'registry.assertion-evidence/v1';
  assuranceProfile: 'evidence-grade';
  subjectBinding: 'audience-scoped';
  requestNonce: string;
  id: string;
  type: 'Evidence';
  supportsRequirement: string;
  isConformantTo: string;
  issuedBy: string;
  providedBy: string;
  issuedAt: string;
  observedAt: string;
  validUntil: string;
  purpose: string;
  audience: string;
  configurationRevision: string;
  subjects: { role: string; binding: string }[];
  supportedValues: { providesValueFor: string; value: unknown }[];
};

export type RawEvidenceResponse = {
  protected: string;
  payload: string;
  signature: string;
};

export type RawApplicationResponse = {
  schema_version: 'solmara-portal-evidence/v1';
  orchestration: {
    service_id: 'citizen-portal';
    decision: 'application_composed';
  };
  signed_evidence: {
    authority: string;
    service_id: string;
    assertion: RawEvidenceResponse;
  }[];
  source_trace: {
    authority: string;
    service_id: string;
    status: number;
    requirements: string[];
  }[];
  derived_decisions: Record<string, boolean | null>;
};

export type RawProviderResponse = RawEvidenceResponse | RawApplicationResponse;

export function requirementId(claimId: string): string {
  return `urn:solmara:requirement:${claimId}:v1`;
}

export function conceptId(claimId: string): string {
  return `urn:solmara:concept:${claimId}`;
}

export function buildEvidenceRequest(
  claimId: string,
  subject: string,
  purpose: string,
  scheme = 'solmara_uin',
  seed = 0
): RawEvidenceRequest {
  void seed;
  return {
    requestNonce: requestNonce(0),
    requirement: requirementId(claimId),
    purpose,
    subjects: [
      {
        role: 'subject',
        selector: {
          profile: scheme === 'farmer_id' ? 'solmara-farmer-v1' : 'solmara-person-v1',
          values: { [scheme]: subject }
        }
      }
    ]
  };
}

export function buildRawRequest(
  scenario: ScenarioResult,
  subject: string,
  seed = 0
): RawEvidenceRequest {
  return buildEvidenceRequest(
    scenario.claimId,
    subject,
    scenario.purpose,
    subjectScheme(scenario),
    seed
  );
}

export function buildEvidenceAssertion(
  scenario: ScenarioResult,
  operationId: string,
  issuedAt: Date,
  claimId = scenario.claimId,
  serviceId = EVIDENCE_SERVICE_ID[scenario.authority],
  value: unknown = scenario.value,
  issuerId: string = scenario.authority
): EvidenceAssertion {
  const requirement = requirementId(claimId);
  return {
    schema: 'registry.assertion-evidence/v1',
    assuranceProfile: 'evidence-grade',
    subjectBinding: 'audience-scoped',
    requestNonce: requestNonce(0),
    id: `urn:solmara:evidence:${operationId}`,
    type: 'Evidence',
    supportsRequirement: requirement,
    isConformantTo: `urn:solmara:evidence-type:${claimId}:v1`,
    issuedBy: `urn:solmara:authority:${issuerId}`,
    providedBy: 'https://evidence.solmara.registrystack.org',
    issuedAt: issuedAt.toISOString(),
    observedAt: `${scenario.asOf}T00:00:00.000Z`,
    validUntil: new Date(
      issuedAt.getTime() + scenario.freshnessDays * 24 * 60 * 60 * 1000
    ).toISOString(),
    purpose: scenario.purpose,
    audience: 'urn:solmara:portal:citizen-services',
    configurationRevision: `sha256:${'a'.repeat(64)}`,
    subjects: [{ role: 'subject', binding: `urn:evidence:subject:v1_${'B'.repeat(43)}` }],
    supportedValues: [{ providesValueFor: conceptId(claimId), value: publicValue(value, scenario) }]
  };
}

export function signEvidence(assertion: EvidenceAssertion, serviceId: string): RawEvidenceResponse {
  return {
    protected: encode({
      alg: 'ES256',
      kid: `${serviceId}-2026-01`,
      typ: 'evidence+jws',
      cty: 'application/evidence+json'
    }),
    payload: encode(assertion),
    signature: SIGNATURE
  };
}

export function buildRawResponse(
  scenario: ScenarioResult,
  operationId: string,
  issuedAt: Date
): RawEvidenceResponse {
  const serviceId = EVIDENCE_SERVICE_ID[scenario.authority];
  return signEvidence(
    buildEvidenceAssertion(scenario, operationId, issuedAt),
    serviceId
  );
}

export function evidenceUrl(scenario: ScenarioResult): string {
  void scenario;
  return 'https://evidence.solmara.registrystack.org/v1/evidence';
}

export function authorityLabel(scenario: ScenarioResult): string {
  return AUTHORITY_LABEL[scenario.authority];
}

export function decodeEvidencePayload(response: RawEvidenceResponse): EvidenceAssertion {
  return JSON.parse(Buffer.from(response.payload, 'base64url').toString('utf8')) as EvidenceAssertion;
}

function requestNonce(seed: number): string {
  const suffix = (seed % 64).toString(36).toUpperCase().padStart(2, '0');
  return `${REQUEST_NONCE_BASE.slice(0, 41)}${suffix}`;
}

function subjectScheme(scenario: ScenarioResult): string {
  return scenario.authority === 'agri' ? 'farmer_id' : 'solmara_uin';
}

function publicValue(value: unknown, scenario: ScenarioResult): unknown {
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return {
      form: 'reviewed-structured-value',
      schema: `urn:solmara:value-schema:${scenario.claimId}:v1`,
      fields: value
    };
  }
  if (value === null) return scenario.state === 'ambiguous' ? 'multiple-matches' : 'not-available';
  return value;
}

function encode(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}
