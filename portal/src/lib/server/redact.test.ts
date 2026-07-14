import { describe, expect, it } from 'vitest';
import {
  containsRawIdentifier,
  pickAllowedMeta,
  redactBody,
  redactRequest,
  redactResponse,
  scrubString
} from './redact';
import { serializeTraceEvent } from './bff';
import type { ProofTrace } from '$lib/types';

// The load-bearing redaction test (spec 5.2 / 10): build a payload containing a
// fixture UIN, a person id, and fake API credentials; run it through the
// redactor AND the SSE serialization; assert NONE of the UIN, /CP-\d+/, or the
// credential strings survive, and that the allowlisted keys DO.

const FAKE_BEARER = 'Bearer eyJhbGciOiJFZERTQSJ9.FAKE_TOKEN_PAYLOAD.FAKE_SIGNATURE_abc123';
const FAKE_API_KEY = 'rn_api_FAKE_TOKEN_PAYLOAD_abc123456789';

// A raw request body shaped like the BFF's un-redacted EvaluateRequest, carrying
// the subject the BFF holds (2300010248) and a delegated dependent (2300036523).
const rawRequest = {
  method: 'POST',
  url: 'https://civil-notary.gov.solmara.example/v1/evaluations',
  body: {
    claims: [{ id: 'person-is-deceased', version: '2026-07' }],
    purpose: 'https://id.registrystack.org/solmara/purpose/pension-payment-review',
    disclosure: 'predicate',
    format: 'application/vnd.registry-notary.claim-result+json',
    relationship: { type: 'self' },
    target: {
      type: 'Person',
      identifiers: [{ scheme: 'solmara_uin', value: '2300010248' }]
    },
    on_behalf_of: {
      actor: { type: 'Person', id_hash: 'hmac-sha256:deadbeef' },
      delegation_ref: 'rnref:v1:REL-1001-MOTHER'
    }
  }
};

// A raw response that echoes a person id (CP-2001) in a target_ref handle, plus a
// freshness timestamp, plus the satisfied predicate.
const rawResponse = {
  status: 200,
  body: {
    results: [
      {
        claim_id: 'person-is-deceased',
        claim_version: '2026-07',
        disclosure: 'predicate',
        evaluation_id: '01HX7Y5F2WAJ7ZP0Q4M5K9E8NC',
        expires_at: '2026-05-25T12:00:00Z',
        issued_at: '2026-05-24T12:00:00Z',
        satisfied: true,
        subject_type: 'person',
        target_ref: {
          handle: 'rnref:v1:CP-2001',
          identifier_schemes: ['solmara_uin'],
          profile: 'resident',
          type: 'Person'
        },
        value: true
      }
    ]
  }
};

describe('scrubString', () => {
  it('blanks UIN, CP, bearer, and x-api-key material', () => {
    const dirty = `subject 2300010248 (CP-2001) with Authorization: ${FAKE_BEARER} and x-api-key: ${FAKE_API_KEY}`;
    const clean = scrubString(dirty);
    expect(clean).not.toContain('2300010248');
    expect(clean).not.toMatch(/CP-\d+/);
    expect(clean).not.toContain('FAKE_TOKEN_PAYLOAD');
    expect(clean).toContain('Bearer •••••••• (redacted)');
    expect(clean).toContain('x-api-key: •••••••• (redacted)');
  });
});

describe('redactBody / request / response', () => {
  it('drops identifier values but keeps the structural key set', () => {
    const red = redactRequest(rawRequest);
    const serialized = JSON.stringify(red);
    // raw identifiers gone
    expect(serialized).not.toContain('2300010248');
    // structural keys preserved (allowlisted wire shape)
    expect(red.body).toHaveProperty('claims');
    expect(red.body).toHaveProperty('purpose', 'https://id.registrystack.org/solmara/purpose/pension-payment-review');
    expect(red.body).toHaveProperty('disclosure', 'predicate');
    expect(red.body).toHaveProperty('relationship');
    // target envelope kept structurally but identifiers stripped
    expect(red.body).toHaveProperty('target');
    const target = red.body.target as { type?: string; identifiers?: unknown[] };
    expect(target.identifiers).toEqual([]);
  });

  it('redacts a response that echoes a person id in a handle', () => {
    const red = redactResponse(rawResponse);
    const serialized = JSON.stringify(red);
    expect(serialized).not.toMatch(/CP-\d+/);
    // allowlisted result keys survive
    const result = (red.body.results as Record<string, unknown>[])[0];
    expect(result).toHaveProperty('claim_id', 'person-is-deceased');
    expect(result).toHaveProperty('satisfied', true);
    expect(result).toHaveProperty('issued_at', '2026-05-24T12:00:00Z');
  });

  it('keeps child application source attribution without a target identifier', () => {
    const red = redactResponse({
      status: 200,
      body: {
        schema_version: 'solmara-child-benefit-evidence/v1',
        evidence_set_id: 'cbe_01TEST',
        orchestration: {
          service_id: 'child-benefit-federator',
          decision: 'not_composed'
        },
        target: {
          type: 'Person',
          identifier_schemes: ['solmara_uin']
        },
        results: [
          {
            claim_id: 'population-record-active',
            notary_service_id: 'nia-notary',
            authority: 'National Identity Agency',
            satisfied: true
          }
        ],
        source_trace: [{ service_id: 'nia-notary', claims: ['population-record-active'] }]
      }
    });

    expect(JSON.stringify(red)).not.toContain('2300010248');
    expect(red.body).toHaveProperty('evidence_set_id', 'cbe_01TEST');
    expect(red.body).toHaveProperty('orchestration.decision', 'not_composed');
    expect(red.body).toHaveProperty(
      'results.0.notary_service_id',
      'nia-notary'
    );
    expect(red.body).toHaveProperty('source_trace.0.service_id', 'nia-notary');
  });

  it('keeps the application-owned survivor decision value', () => {
    const red = redactResponse({
      status: 200,
      body: {
        schema_version: 'solmara-portal-evidence/v1',
        derived_decisions: { 'survivor-benefit-eligible': true }
      }
    });

    expect(red.body).toHaveProperty(
      'derived_decisions.survivor-benefit-eligible',
      true
    );
  });
});

describe('SSE serialization is identifier-free end to end', () => {
  it('produces an event frame with no UIN / CP / bearer material', () => {
    const trace: ProofTrace = {
      id: 'event 1',
      seq: 1,
      fieldId: 'person-is-deceased',
      authority: 'civil',
      headline: 'Confirmed by Civil Registry',
      answered: 'Civil Registry answered: person-is-deceased = true',
      notDisclosed: 'Not disclosed: any other civil record detail',
      status: 'ok',
      ts: '2026-06-21T10:00:00.000Z',
      request: redactRequest(rawRequest),
      response: redactResponse(rawResponse)
    };
    const frame = serializeTraceEvent(trace);

    // the streamed bytes carry NONE of the secrets / identifiers
    expect(frame).not.toContain('2300010248');
    expect(frame).not.toMatch(/CP-\d+/);
    expect(frame).not.toContain('FAKE_TOKEN_PAYLOAD');
    expect(frame).not.toContain(FAKE_API_KEY);
    expect(containsRawIdentifier(frame)).toBe(false);

    // but the allowlisted, structural content DID survive
    expect(frame).toContain('person-is-deceased');
    expect(frame).toContain('https://id.registrystack.org/solmara/purpose/pension-payment-review');
    expect(frame).toContain('Not disclosed:');
    expect(frame.startsWith('event: trace\ndata: ')).toBe(true);
  });
});

describe('pickAllowedMeta', () => {
  it('keeps only allowlisted keys and scrubs their values', () => {
    const picked = pickAllowedMeta({
      claim: 'person-is-deceased',
      purpose: 'https://id.registrystack.org/solmara/purpose/pension-payment-review',
      disclosure: 'predicate',
      authority: 'Civil Registry',
      result: 'true',
      freshness: '2026-05-24',
      // these must be dropped
      bearer: FAKE_BEARER,
      api_key: FAKE_API_KEY,
      target: '2300010248',
      subject: 'CP-2001'
    });
    expect(Object.keys(picked).sort()).toEqual(
      ['authority', 'claim', 'disclosure', 'freshness', 'purpose', 'result'].sort()
    );
    expect(JSON.stringify(picked)).not.toContain('2300010248');
    expect(JSON.stringify(picked)).not.toMatch(/CP-\d+/);
    expect(JSON.stringify(picked)).not.toContain('FAKE_TOKEN_PAYLOAD');
  });
});

describe('redactBody catches a leaked identifier inside an allowlisted value', () => {
  it('scrubs a UIN embedded in an otherwise-allowed string value', () => {
    const leaked = redactBody({
      purpose: 'lookup for 2300010248',
      value: 'belongs to CP-2001'
    });
    const serialized = JSON.stringify(leaked);
    expect(serialized).not.toContain('2300010248');
    expect(serialized).not.toMatch(/CP-\d+/);
  });
});
