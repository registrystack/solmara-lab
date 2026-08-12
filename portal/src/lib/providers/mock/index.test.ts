import { describe, expect, it } from 'vitest';
import type { EvaluateContext } from '$lib/providers/EvidenceProvider';
import type { Field } from '$lib/types';
import { MockEvidenceProvider, PERSONA } from './index';
import {
  decodeEvidencePayload,
  EVIDENCE_RESPONSE_FORMAT,
  type RawApplicationRequest,
  type RawApplicationResponse,
  type RawEvidenceRequest,
  type RawEvidenceResponse
} from './wire';

const provider = new MockEvidenceProvider();
const ctx: EvaluateContext = { subject: PERSONA.elena };

function field(id: string): Field {
  return { id, label: id, kind: 'verify' };
}

describe('MockEvidenceProvider.evaluate', () => {
  it('returns a verified authority result for a true predicate', async () => {
    const result = await provider.evaluate(field('registered-farmer'), ctx);
    expect(result).toMatchObject({ state: 'verified', authority: 'agri' });
    expect(result.traceId).toMatch(/^event \d+$/);
  });

  it('keeps a portal-composed decision separate from authority assertions', async () => {
    const evaluation = await provider.evaluateDetailed(field('combined-support-eligibility'), ctx);
    expect(evaluation.result.state).toBe('verified');
    expect(evaluation.result.authority).toBeUndefined();
    expect(evaluation.proof.authority).toBeUndefined();
    expect(evaluation.raw.request.method).toBe('MULTI');

    const request = evaluation.raw.request.body as RawApplicationRequest;
    const response = evaluation.raw.response.body as RawApplicationResponse;
    expect(request.requests.map((source) => source.service_id)).toEqual([
      'cra-evidence',
      'sipf-evidence',
      'sipf-evidence'
    ]);
    expect(request.requests.map((source) => source.body.requirement)).toEqual([
      'urn:solmara:requirement:person-is-deceased:v1',
      'urn:solmara:requirement:pension-payment-active:v1',
      'urn:solmara:requirement:survivor-is-eligible:v1'
    ]);
    expect(response.signed_evidence).toHaveLength(3);
    expect(response.derived_decisions).toEqual({ 'survivor-benefit-eligible': true });
  });

  it('returns the verified pension-stop decision composed from its two authority requirements', async () => {
    const evaluation = await provider.evaluateDetailed(field('disability-determination'), ctx);
    expect(evaluation.result.state).toBe('verified');
    expect(evaluation.result.display).toContain('Pension payment should stop');
    expect(evaluation.result.authority).toBeUndefined();

    const request = evaluation.raw.request.body as RawApplicationRequest;
    expect(request.requests.map((source) => source.body.requirement)).toEqual([
      'urn:solmara:requirement:person-is-deceased:v1',
      'urn:solmara:requirement:pension-payment-active:v1'
    ]);
  });

  it('returns the delegated child-age predicate as minimized signed Evidence', async () => {
    const evaluation = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: true
    });
    expect(evaluation.result).toMatchObject({ state: 'verified', authority: 'childCivil' });
    const assertion = decodeEvidencePayload(evaluation.raw.response.body as RawEvidenceResponse);
    expect(assertion.supportedValues).toEqual([
      { providesValueFor: 'urn:solmara:concept:child-age-under-5', value: true }
    ]);
  });

  it('returns the population predicate from NIA Evidence with canonical attribution', async () => {
    const evaluation = await provider.evaluateDetailed(field('population-record-active'), ctx, {
      guardianLinkVerified: true
    });
    expect(evaluation.result).toMatchObject({
      state: 'verified',
      display: 'Population record active: yes',
      authority: 'population'
    });
    const assertion = decodeEvidencePayload(evaluation.raw.response.body as RawEvidenceResponse);
    expect(assertion).toMatchObject({
      supportsRequirement: 'urn:solmara:requirement:population-record-active:v1',
      issuedBy: 'did:web:id.registrystack.org:solmara:authority:nia',
      providedBy: 'https://nia-evidence.solmara.registrystack.org/'
    });
  });

  it('keeps citizen-record readiness portal-owned without inventing certificate facts', async () => {
    const evaluation = await provider.evaluateDetailed(field('citizen-record-status'), ctx);
    expect(evaluation.result.state).toBe('verified');
    expect(evaluation.result.authority).toBeUndefined();
    expect(evaluation.proof.authority).toBeUndefined();

    const response = evaluation.raw.response.body as RawApplicationResponse;
    expect(response.signed_evidence.map((source) => source.authority)).toEqual([
      'Civil Registration Authority',
      'National Identity Agency'
    ]);
    expect(response.derived_decisions).toEqual({ 'citizen-self-service-ready': true });
    expect(JSON.stringify(evaluation)).not.toMatch(/certificate_id|issued_on|CSR-BIRTH/);
  });
});

describe('portal authorization gates', () => {
  it('denies a cross-person request before authority Evidence is called', async () => {
    const evaluation = await provider.evaluateDetailed(field('denial'), ctx);
    expect(evaluation.raw.response).toMatchObject({ status: 403 });
    expect(evaluation.raw.response.body).toMatchObject({
      type: 'urn:solmara:portal:problem:not_authorized',
      status: 403
    });
    expect(evaluation.raw.request.url).toBe('solmara://citizen-portal/blocked-before-authority-call');
    expect(evaluation.proof).toMatchObject({
      status: 'denied',
      authority: undefined,
      crypto: {
        signedBy: 'Portal authorization gate; authority Evidence was not called',
        credential: 'No credential or Evidence assertion returned'
      }
    });
  });

  it('denies a dependent read until the guardian link is proven', async () => {
    const denied = await provider.evaluateDetailed(field('date-of-birth'), ctx);
    expect(denied.raw.response.status).toBe(403);
    expect(denied.raw.response.body).not.toHaveProperty('protected');

    const allowed = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: true
    });
    expect(allowed.raw.response.status).toBe(200);
    const request = allowed.raw.request.body as RawEvidenceRequest;
    expect(request.requirement).toBe('urn:solmara:requirement:child-age-under-5:v1');
    expect(request.subjects[0].selector.values.solmara_uin).toBe(PERSONA.mateo);
  });

  it('denies a dependent read when the guardian link is explicitly false', async () => {
    const evaluation = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: false
    });
    expect(evaluation.result).toMatchObject({
      state: 'error',
      reasonCode: 'relationship_not_proven'
    });
    expect(evaluation.raw.response.status).toBe(403);
    expect(evaluation.proof.crypto.signedBy).toBe(
      'Portal authorization gate; authority Evidence was not called'
    );
  });

  it('retains the attempted selector only server-side on a cross-person denial', async () => {
    const evaluation = await provider.evaluateDetailed(field('denial'), ctx);
    const request = evaluation.raw.request.body as RawEvidenceRequest;
    expect(evaluation.result.reasonCode).toBe('not_authorized');
    expect(request.subjects[0].selector.values.solmara_uin).toBe(PERSONA.karim);
    expect(evaluation.raw.response.body).not.toHaveProperty('protected');
    expect(evaluation.raw.response.body).not.toHaveProperty('signed_evidence');
  });
});

describe('authority Evidence wire contract', () => {
  it('uses EvidenceRequest v1 keys and the /v1/evidence route', async () => {
    const evaluation = await provider.evaluateDetailed(field('registered-farmer'), ctx);
    const request = evaluation.raw.request.body as RawEvidenceRequest;

    expect(evaluation.raw.request.url).toBe('https://nagdi-evidence.solmara.registrystack.org/v1/evidence');
    expect(Object.keys(request)).toEqual([
      'requestNonce',
      'requirement',
      'purpose',
      'subjects'
    ]);
    expect(request.requestNonce).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(request.requirement).toBe('urn:solmara:requirement:farmer-registered:v1');
    expect(request.purpose).toBe('voucher-eligibility-review');
    expect(request.subjects[0]).toMatchObject({
      role: 'subject',
      selector: { profile: 'solmara-farmer-v1' }
    });
  });

  it('returns a flattened JWS carrying an Evidence assertion payload', async () => {
    const evaluation = await provider.evaluateDetailed(field('registered-farmer'), ctx);
    const response = evaluation.raw.response.body as RawEvidenceResponse;
    expect(Object.keys(response)).toEqual(['protected', 'payload', 'signature']);
    expect(response.signature).toMatch(/^[A-Za-z0-9_-]{86}$/);

    const assertion = decodeEvidencePayload(response);
    expect(assertion).toMatchObject({
      schema: 'registry.assertion-evidence/v1',
      assuranceProfile: 'evidence-grade',
      subjectBinding: 'audience-scoped',
      type: 'Evidence',
      supportsRequirement: 'urn:solmara:requirement:farmer-registered:v1',
      purpose: 'voucher-eligibility-review'
    });
    expect(assertion.supportedValues).toEqual([
      { providesValueFor: 'urn:solmara:concept:farmer-registered', value: true }
    ]);
    expect(EVIDENCE_RESPONSE_FORMAT).toBe('application/jose+json');
    expect(evaluation.proof.crypto).toMatchObject({
      algorithm: 'Flattened JWS, ES256',
      issuerKey: '/.well-known/evidence/jwks.json',
      credential: 'Signed minimum-disclosure Evidence assertion'
    });
  });

  it('encodes a reviewed decision object as an Evidence structured value', async () => {
    const evaluation = await provider.evaluateDetailed(field('voucher-eligibility'), ctx);
    const assertion = decodeEvidencePayload(evaluation.raw.response.body as RawEvidenceResponse);
    expect(assertion.supportedValues).toEqual([
      {
        providesValueFor: 'urn:solmara:concept:eligible-for-climate-smart-input-voucher',
        value: {
          form: 'reviewed-structured-value',
          schema: 'urn:solmara:value-schema:eligible-for-climate-smart-input-voucher:v1',
          fields: { eligible: true, voucher_tier: 'standard' }
        }
      }
    ]);
    expect(JSON.stringify(assertion)).not.toContain('parcel');
  });

  it('keeps authority Evidence service identity aligned with each legal issuer', async () => {
    const evaluation = await provider.evaluateDetailed(field('combined-support-eligibility'), ctx);
    const response = evaluation.raw.response.body as RawApplicationResponse;
    expect(response.signed_evidence.map((source) => source.service_id)).toEqual([
      'cra-evidence',
      'sipf-evidence',
      'sipf-evidence'
    ]);
    expect(
      response.signed_evidence.map((source) => decodeEvidencePayload(source.assertion).issuedBy)
    ).toEqual([
      'did:web:id.registrystack.org:solmara:authority:cra',
      'did:web:id.registrystack.org:solmara:authority:sipf',
      'did:web:id.registrystack.org:solmara:authority:sipf'
    ]);
    expect(
      response.signed_evidence.map((source) => decodeEvidencePayload(source.assertion).providedBy)
    ).toEqual([
      'https://cra-evidence.solmara.registrystack.org/',
      'https://sipf-evidence.solmara.registrystack.org/',
      'https://sipf-evidence.solmara.registrystack.org/'
    ]);
  });

  it('uses the CRA Evidence endpoint and signed proof contract for child predicates', async () => {
    const evaluation = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: true
    });
    expect(evaluation.raw.request.url).toBe('https://cra-evidence.solmara.registrystack.org/v1/evidence');
    expect(evaluation.proof.crypto).toMatchObject({
      signedBy: 'Civil Registration Authority Evidence',
      algorithm: 'Flattened JWS, ES256',
      issuerKey: '/.well-known/evidence/jwks.json',
      credential: 'Signed minimum-disclosure Evidence assertion'
    });
  });
});

describe('resilience states', () => {
  it('flags a slow call without changing its eventual verified result', async () => {
    const evaluation = await provider.evaluateDetailed(field('slow'), ctx);
    expect(evaluation.timing.slow).toBe(true);
    expect(evaluation.result.state).toBe('verified');
  });

  it('scopes an unavailable Evidence service to the field', async () => {
    const evaluation = await provider.evaluateDetailed(field('error'), ctx);
    expect(evaluation.result.state).toBe('error');
    expect(evaluation.raw.response.status).toBe(503);
    expect(evaluation.proof.crypto.signedBy).toBe(
      'No Evidence assertion; Social Registry Office was unavailable'
    );
  });

  it('never collapses an ambiguous source match to false', async () => {
    const evaluation = await provider.evaluateDetailed(field('ambiguous'), ctx);
    expect(evaluation.result.state).toBe('ambiguous');
  });

  it('preserves stale assertion timestamps for the freshness warning', async () => {
    const evaluation = await provider.evaluateDetailed(field('stale'), ctx);
    const assertion = decodeEvidencePayload(evaluation.raw.response.body as RawEvidenceResponse);
    expect(evaluation.result).toMatchObject({ state: 'stale', asOf: '2025-09-30' });
    expect(Date.parse(assertion.issuedAt)).toBeLessThan(Date.parse(assertion.validUntil));
    expect(Date.parse(assertion.validUntil)).toBeLessThan(Date.now());
  });

  it('returns the current Evidence problem shape when the authority service is unavailable', async () => {
    const evaluation = await provider.evaluateDetailed(field('error'), ctx);
    expect(evaluation.result.reasonCode).toBe('service_unavailable');
    expect(evaluation.raw.response.body).toMatchObject({
      type: 'https://registrystack.org/problems/evidence/service_unavailable',
      title: 'Authority Evidence is unavailable',
      status: 503
    });
    expect(evaluation.raw.response.body).not.toHaveProperty('signature');
  });
});
