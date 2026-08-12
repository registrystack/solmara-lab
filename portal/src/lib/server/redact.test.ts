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

const FAKE_BEARER = 'Bearer eyJhbGciOiJFZERTQSJ9.FAKE_TOKEN_PAYLOAD.FAKE_SIGNATURE_abc123';
const FAKE_API_KEY = 'rn_api_FAKE_TOKEN_PAYLOAD_abc123456789';

const rawRequest = {
  method: 'POST',
  url: 'https://evidence.solmara.registrystack.org/v1/evidence',
  body: {
    requestNonce: 'U29sbWFyYVJlZ2lzdHJ5RXZpZGVuY2VEZW1vMDAwMDE',
    requirement: 'urn:solmara:requirement:person-is-deceased:v1',
    purpose: 'pension-payment-review',
    subjects: [
      {
        role: 'subject',
        selector: {
          profile: 'solmara-person-v1',
          values: { solmara_uin: '2300010248', farmer_id: 'FR-1001' }
        }
      }
    ]
  }
};

const rawResponse = {
  status: 200,
  body: {
    protected: 'eyJhbGciOiJFUzI1NiJ9',
    payload: 'c3ludGhldGljLWV2aWRlbmNlLXBheWxvYWQ',
    signature: 'A'.repeat(86)
  }
};

describe('scrubString', () => {
  it('blanks UIN, source ids, bearer, and API-key material', () => {
    const dirty = `subject 2300010248 (CP-2001, FR-1001) with Authorization: ${FAKE_BEARER} and x-api-key: ${FAKE_API_KEY}`;
    const clean = scrubString(dirty);
    expect(clean).not.toMatch(/2300010248|CP-2001|FR-1001|FAKE_TOKEN_PAYLOAD/);
    expect(clean).toContain('Bearer •••••••• (redacted)');
    expect(clean).toContain('x-api-key: •••••••• (redacted)');
  });
});

describe('Registry Evidence request and response redaction', () => {
  it('keeps the Evidence request shape and strips selector values', () => {
    const redacted = redactRequest(rawRequest);
    expect(redacted.body).toMatchObject({
      requirement: 'urn:solmara:requirement:person-is-deceased:v1',
      purpose: 'pension-payment-review',
      subjects: [
        {
          role: 'subject',
          selector: {
            profile: 'solmara-person-v1',
            values: {
              solmara_uin: '••••(redacted)',
              farmer_id: '••••(redacted)'
            }
          }
        }
      ]
    });
    expect(JSON.stringify(redacted)).not.toMatch(/2300010248|FR-1001/);
  });

  it('keeps the signed flattened JWS artifact', () => {
    const redacted = redactResponse(rawResponse);
    expect(redacted.body).toEqual(rawResponse.body);
  });

  it('keeps portal composition attribution and Evidence service ids', () => {
    const redacted = redactResponse({
      status: 200,
      body: {
        schema_version: 'solmara-portal-evidence/v1',
        orchestration: { service_id: 'citizen-portal', decision: 'application_composed' },
        signed_evidence: [
          {
            authority: 'National Identity Agency',
            service_id: 'registry-evidence',
            assertion: rawResponse.body
          }
        ],
        source_trace: [
          {
            service_id: 'registry-evidence',
            requirements: ['urn:solmara:requirement:population-record-active:v1']
          }
        ],
        derived_decisions: { 'citizen-self-service-ready': true }
      }
    });

    expect(redacted.body).toHaveProperty('signed_evidence.0.service_id', 'registry-evidence');
    expect(redacted.body).toHaveProperty('source_trace.0.service_id', 'registry-evidence');
    expect(redacted.body).toHaveProperty('derived_decisions.citizen-self-service-ready', true);
  });
});

describe('SSE serialization', () => {
  it('is identifier-free while retaining the Evidence contract', () => {
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

    expect(frame).not.toMatch(/2300010248|FR-1001|FAKE_TOKEN_PAYLOAD/);
    expect(containsRawIdentifier(frame)).toBe(false);
    expect(frame).toContain('urn:solmara:requirement:person-is-deceased:v1');
    expect(frame).toContain('pension-payment-review');
    expect(frame.startsWith('event: trace\ndata: ')).toBe(true);
  });
});

describe('pickAllowedMeta', () => {
  it('keeps only allowlisted keys and scrubs their values', () => {
    const picked = pickAllowedMeta({
      claim: 'person-is-deceased',
      purpose: 'pension-payment-review',
      disclosure: 'predicate',
      authority: 'Civil Registry',
      result: 'true',
      freshness: '2026-05-24',
      bearer: FAKE_BEARER,
      target: '2300010248'
    });
    expect(Object.keys(picked).sort()).toEqual(
      ['authority', 'claim', 'disclosure', 'freshness', 'purpose', 'result'].sort()
    );
    expect(JSON.stringify(picked)).not.toContain('2300010248');
  });
});

describe('redactBody defense in depth', () => {
  it('scrubs an identifier embedded in an allowlisted value', () => {
    const leaked = redactBody({ purpose: 'review for 2300010248' });
    expect(JSON.stringify(leaked)).not.toContain('2300010248');
  });
});
