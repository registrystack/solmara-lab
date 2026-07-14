import { describe, expect, it } from 'vitest';
import type { EvaluateContext } from '$lib/providers/EvidenceProvider';
import type { Field } from '$lib/types';
import { MockEvidenceProvider, PERSONA } from './index';
import {
  CHILD_BENEFIT_FORMAT,
  type RawApplicationRequest,
  type RawApplicationResponse,
  type RawChildBenefitRequest,
  type RawEvaluateRequest
} from './wire';

const provider = new MockEvidenceProvider();
const ctx: EvaluateContext = { subject: PERSONA.elena };

function field(id: string): Field {
  return { id, label: id, kind: 'verify' };
}

describe('MockEvidenceProvider.evaluate', () => {
  it('returns a GREEN verified state for a true predicate', async () => {
    const res = await provider.evaluate(field('registered-farmer'), ctx);
    expect(res.state).toBe('verified');
    expect(res.authority).toBe('agri');
    expect(res.traceId).toMatch(/^event \d+$/);
  });

  it('returns a verified pension stop predicate', async () => {
    const res = await provider.evaluate(field('disability-determination'), ctx);
    expect(res.state).toBe('verified');
    expect(res.display).toContain('Pension payment should stop');
    expect(res.authority).toBeUndefined();
  });

  it('returns a delegated child age predicate', async () => {
    // date-of-birth is the legacy field key for the age predicate, so the
    // guardian link must be proven for the value to be returned.
    const ev = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: true
    });
    expect(ev.result.state).toBe('verified');
    // The child application returns minimized predicates without a duplicate value field.
    const view = ev.raw.response.body as { results: { satisfied: boolean }[] };
    expect(view.results[0].satisfied).toBe(true);
  });

  it('returns the missing population source predicate', async () => {
    const ev = await provider.evaluateDetailed(field('population-record-active'), ctx, {
      guardianLinkVerified: true
    });
    expect(ev.result).toMatchObject({
      state: 'verified',
      display: 'Population record active: yes',
      authority: 'population'
    });
    // The child application response is a predicate-only evidence set.
    const view = ev.raw.response.body as {
      results: { claim_id: string; satisfied: boolean }[];
    };
    expect(view.results[0]).toMatchObject({
      claim_id: 'population-record-active',
      satisfied: true
    });
  });

  it('returns a boolean citizen-record decision without inventing certificate facts', async () => {
    const ev = await provider.evaluateDetailed(field('citizen-record-status'), ctx);
    expect(ev.result.state).toBe('verified');
    expect(ev.result.authority).toBeUndefined();
    expect(ev.proof.authority).toBeUndefined();
    const view = ev.raw.response.body as RawApplicationResponse;
    expect(view.results.map((result) => result.provenance.generated_by.service_id)).toEqual([
      'cra-notary',
      'nia-notary'
    ]);
    expect(view.derived_decisions).toEqual({ 'citizen-self-service-ready': true });
    expect(JSON.stringify(ev)).not.toMatch(/certificate_id|issued_on|CSR-BIRTH/);
  });

  it('mirrors live multi-authority requests instead of fabricating a Notary-owned decision', async () => {
    const ev = await provider.evaluateDetailed(field('combined-support-eligibility'), ctx);
    expect(ev.result.state).toBe('verified');
    expect(ev.result.authority).toBeUndefined();
    expect(ev.proof.authority).toBeUndefined();
    expect(ev.raw.request.method).toBe('MULTI');
    const request = ev.raw.request.body as RawApplicationRequest;
    const view = ev.raw.response.body as RawApplicationResponse;
    expect(request.requests.map((source) => source.service_id)).toEqual([
      'cra-notary',
      'sipf-notary',
      'sipf-notary'
    ]);
    expect(request.requests.map((source) => source.body.claims[0])).toEqual([
      'person-is-deceased',
      'pension-payment-active',
      'survivor-is-eligible'
    ]);
    expect(view.results.map((result) => result.claim_id)).toEqual([
      'person-is-deceased',
      'pension-payment-active',
      'survivor-is-eligible'
    ]);
    expect(view.derived_decisions).toEqual({ 'survivor-benefit-eligible': true });
    expect(JSON.stringify(ev)).not.toContain('support_band');
  });
});

describe('denial beat (cross-person stranger)', () => {
  it('produces a 403 subject_mismatch with NO source read', async () => {
    const ev = await provider.evaluateDetailed(field('denial'), ctx);
    expect(ev.result.state).toBe('error');
    expect(ev.result.reasonCode).toBe('subject_mismatch');
    // 403 shape, no 200 results body
    expect(ev.raw.response.status).toBe(403);
    expect(ev.raw.response.body).not.toHaveProperty('results');
    expect(ev.raw.response.body).toHaveProperty('error', 'subject_mismatch');
    // the proof status is a denial; the rail will bounce
    expect(ev.proof.status).toBe('denied');
    expect(ev.result.authority).toBeUndefined();
    expect(ev.proof.authority).toBeUndefined();
    expect(ev.proof.headline).toBe(
      'Portal denied the cross-person request before any authority call'
    );
    expect(ev.raw.request.url).toBe('solmara://citizen-portal/blocked-before-authority-call');
    expect(ev.proof.answered).toContain('before any authority call');
    expect(ev.proof.crypto).toMatchObject({
      signedBy: 'Portal authorization gate; no authority Notary called',
      credential: 'No credential or evidence result returned'
    });
    // the request targeted the stranger, never the session subject
    // Denial scenarios use a single authority request, never an application batch.
    const target = (ev.raw.request.body as RawEvaluateRequest).target;
    expect(target.identifiers[0].value).toBe(PERSONA.karim);
  });

  it('does not perform a source read (no source_count > 0 on a denial)', async () => {
    const ev = await provider.evaluateDetailed(field('denial'), ctx);
    // there is no 200 results body at all, so no source was read
    expect(ev.raw.response.body).not.toHaveProperty('results');
  });

  it('preserves the configured disclosure on direct authority responses', async () => {
    const ev = await provider.evaluateDetailed(field('voucher-eligibility'), ctx);
    const view = ev.raw.response.body as { results: { disclosure: string }[] };
    expect(view.results[0].disclosure).toBe('decision');
  });
});

describe('delegated two-hop gate', () => {
  it('denies a civil read before the guardian link is proven (no dependent read)', async () => {
    const ev = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: false
    });
    expect(ev.result.state).toBe('error');
    expect(ev.raw.response.status).toBe(403);
    expect(ev.raw.response.body).not.toHaveProperty('results');
    expect(ev.proof.status).toBe('denied');
    expect(ev.proof.crypto.signedBy).toBe('Portal authorization gate; no authority Notary called');
  });

  it('denies a delegated civil read when the guardian flag is omitted (deny by default)', async () => {
    const ev = await provider.evaluateDetailed(field('date-of-birth'), ctx);
    expect(ev.result.state).toBe('error');
    expect(ev.raw.response.status).toBe(403);
    expect(ev.raw.response.body).not.toHaveProperty('results');
    expect(ev.proof.status).toBe('denied');
  });

  it('authorizes the civil read once the guardian link is proven', async () => {
    const ev = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: true
    });
    expect(ev.result.state).toBe('verified');
    expect(ev.raw.response.status).toBe(200);
    // The portal gate authorizes the read before the clean federator request is built.
    // Child scenarios use the application request variant of the provider union.
    const body = ev.raw.request.body as RawChildBenefitRequest;
    expect(body.on_behalf_of).toBeUndefined();
    expect(body.target.identifiers[0].value).toBe(PERSONA.mateo);
  });
});

describe('resilience states', () => {
  it('flags a slow call (>= 6s budget) before it resolves verified', async () => {
    const ev = await provider.evaluateDetailed(field('slow'), ctx);
    expect(ev.timing.slow).toBe(true);
    expect(ev.result.state).toBe('verified');
  });

  it('lands an upstream failure in ERROR with no source read', async () => {
    const ev = await provider.evaluateDetailed(field('error'), ctx);
    expect(ev.result.state).toBe('error');
    expect(ev.raw.response.status).toBe(503);
    expect(ev.raw.response.body).not.toHaveProperty('results');
    expect(ev.proof.crypto).toMatchObject({
      signedBy: 'No claim result; Social Registry Office was unavailable',
      credential: 'No credential or evidence result returned'
    });
  });

  it('marks a fetched-but-old value as stale', async () => {
    const ev = await provider.evaluateDetailed(field('stale'), ctx);
    expect(ev.result.state).toBe('stale');
    const view = ev.raw.response.body as { results: { issued_at: string; expires_at: string }[] };
    expect(Date.parse(view.results[0].issued_at)).toBeLessThan(Date.parse(view.results[0].expires_at));
    expect(Date.parse(view.results[0].expires_at)).toBeLessThan(Date.now());
  });

  it('never collapses an ambiguous match to false', async () => {
    const ev = await provider.evaluateDetailed(field('ambiguous'), ctx);
    expect(ev.result.state).toBe('ambiguous');
  });
});

describe('structural match to the Notary OpenAPI', () => {
  // The depth-2 bodies must carry the same key set as EvaluateRequest /
  // EvaluationResponse -> ClaimResultView. We assert the required key sets here so
  // a drift from the OpenAPI fails loudly.
  it('request body matches EvaluateRequest key set', async () => {
    const ev = await provider.evaluateDetailed(field('registered-farmer'), ctx);
    // The agriculture scenario uses a single Registry Notary request.
    const body = ev.raw.request.body as Record<string, unknown>;
    expect(Object.keys(body)).toEqual([
      'claims',
      'purpose',
      'disclosure',
      'format',
      'relationship',
      'target'
    ]);
    expect(body.claims).toEqual(['farmer-registered']);
  });

  it('200 response result matches the ClaimResultView required key set', async () => {
    const ev = await provider.evaluateDetailed(field('registered-farmer'), ctx);
    // The agriculture scenario uses the mock ClaimResultView response variant.
    const view = (ev.raw.response.body as { results: Record<string, unknown>[] }).results[0];
    // every required key from the OpenAPI ClaimResultView is present
    for (const key of [
      'evaluation_id',
      'claim_id',
      'claim_version',
      'subject_type',
      'target_ref',
      'value',
      'satisfied',
      'disclosure',
      'format',
      'issued_at',
      'expires_at',
      'provenance'
    ]) {
      expect(view).toHaveProperty(key);
    }
    // Provenance is asserted structurally after the required top-level key check.
    const prov = view.provenance as Record<string, unknown>;
    expect(prov).toHaveProperty('schema_version', 'registry-notary-claim-provenance/v2');
    expect(prov).toHaveProperty('generated_by');
    expect(prov).toHaveProperty('used');
    expect(prov).toHaveProperty('derived_from');
  });

  it('uses the ordinary child application evidence request and source-attributed proof contract', async () => {
    const ev = await provider.evaluateDetailed(field('date-of-birth'), ctx, {
      guardianLinkVerified: true
    });
    expect(ev.raw.request).toEqual({
      method: 'POST',
      url: 'https://child-benefit-federator.solmara.registrystack.org/v1/evaluations',
      body: {
        target: {
          type: 'Person',
          identifiers: [{ scheme: 'solmara_uin', value: PERSONA.mateo }]
        },
        claims: ['child-age-under-5'],
        disclosure: 'predicate',
        format: CHILD_BENEFIT_FORMAT
      }
    });
    expect(ev.proof.crypto).toMatchObject({
      signedBy:
        'Civil Registration Authority source result collected by child-benefit-federator',
      algorithm: 'Ordinary JSON response; no application signature asserted',
      issuerKey: 'Not applicable for an application evidence set',
      holderBound: 'Purpose- and subject-bound child-benefit evidence request',
      credential: 'Minimized source-attributed predicate result'
    });
    expect(JSON.stringify(ev.proof.crypto)).not.toMatch(
      /federated|federation|SD-JWT|notary:citizen/
    );
  });
});
