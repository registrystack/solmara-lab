// Canned ProofTrace[] for the proof gallery demo and unit tests.
// Every ProofStatus and depth shape is represented.
import type { ProofTrace } from '$lib/types';

export const CANNED_TRACES: ProofTrace[] = [
  // 1. In-flight (skeleton at top)
  {
    id: 'event-1',
    seq: 1,
    fieldId: 'farmer-registered',
    authority: 'agri',
    headline: 'Checking NAgDI for farmer-registered status...',
    answered: 'Agriculture answered: farmer-registered = (pending)',
    notDisclosed: 'Only the yes/no result is checked, no farm details',
    status: 'in_flight',
    ts: '2026-06-21T12:04:05.000Z',
    request: {
      method: 'POST',
      url: 'https://evidence.solmara.example/v1/evidence',
      body: {
        requestNonce: 'U29sbWFyYVJlZ2lzdHJ5RXZpZGVuY2VEZW1vMDAwMDE',
        requirement: 'urn:solmara:requirement:farmer-registered:v1',
        purpose: 'voucher-eligibility-review',
        subjects: [{ role: 'subject', selector: { profile: 'solmara-farmer-v1', values: {} } }]
      }
    }
  },

  // 2. Verified (farmer registration)
  {
    id: 'event-2',
    seq: 2,
    fieldId: 'farmer-registered',
    authority: 'agri',
    headline:
      'Confirmed by NAgDI: Amina did not have to prove this herself',
    answered: 'Agriculture answered: farmer-registered = true',
    notDisclosed: 'Only the yes/no, no farm details or parcel coordinates',
    status: 'ok',
    ts: '2026-06-21T12:04:09.000Z',
    request: {
      method: 'POST',
      url: 'https://evidence.solmara.example/v1/evidence',
      body: {
        requestNonce: 'U29sbWFyYVJlZ2lzdHJ5RXZpZGVuY2VEZW1vMDAwMDE',
        requirement: 'urn:solmara:requirement:farmer-registered:v1',
        purpose: 'voucher-eligibility-review',
        subjects: [{ role: 'subject', selector: { profile: 'solmara-farmer-v1', values: {} } }]
      }
    },
    response: {
      status: 200,
      body: {
        protected: 'eyJhbGciOiJFUzI1NiIsInR5cCI6ImV2aWRlbmNlK2p3cyJ9',
        payload: 'c3ludGhldGljLWV2aWRlbmNlLXBheWxvYWQ',
        signature: 'synthetic-signature-redacted'
      }
    },
    proof: {
      signedBy: 'National Agricultural Data Institute through Registry Evidence',
      algorithm: 'Flattened JWS, ES256',
      issuerKey: '/.well-known/evidence/jwks.json',
      holderBound: 'Audience-scoped to the portal requester, purpose, nonce, and subject binding',
      credential: 'Signed minimum-disclosure Evidence assertion',
      auditId: 'evidence:event-2'
    }
  },

  // 3. Fetched (household composition)
  {
    id: 'event-3',
    seq: 3,
    fieldId: 'household-below-poverty-threshold',
    authority: 'socialRegistry',
    headline:
      'Verified by Social Protection: household is below the programme threshold',
    answered: 'Social answered: household-below-poverty-threshold = true',
    notDisclosed: 'Predicate only, not poverty score or household roster',
    status: 'ok',
    ts: '2026-06-21T12:04:12.000Z',
    request: {
      method: 'POST',
      url: 'https://evidence.solmara.example/v1/evidence',
      body: {
        requestNonce: 'U29sbWFyYVJlZ2lzdHJ5RXZpZGVuY2VEZW1vMDAwMDI',
        requirement: 'urn:solmara:requirement:household-below-poverty-threshold:v1',
        purpose: 'child-benefit-review',
        subjects: [{ role: 'subject', selector: { profile: 'solmara-person-v1', values: {} } }]
      }
    },
    response: {
      status: 200,
      body: {
        protected: 'eyJhbGciOiJFUzI1NiIsInR5cCI6ImV2aWRlbmNlK2p3cyJ9',
        payload: 'c3ludGhldGljLWV2aWRlbmNlLXBheWxvYWQ',
        signature: 'synthetic-signature-redacted'
      }
    },
    proof: {
      signedBy: 'Social Registry Office through Registry Evidence',
      algorithm: 'Flattened JWS, ES256',
      issuerKey: '/.well-known/evidence/jwks.json',
      holderBound: 'Audience-scoped to the portal requester, purpose, nonce, and subject binding',
      credential: 'Signed minimum-disclosure Evidence assertion',
      auditId: 'evidence:event-3'
    }
  },

  // 4. Denial (cross-person attempt)
  {
    id: 'event-4',
    seq: 4,
    fieldId: 'person-is-deceased',
    authority: 'civil',
    headline: 'Denied by the portal: request was not authorized, no data read',
    answered: 'Portal authorization gate answered: request = denied (not_authorized)',
    notDisclosed:
      'No data was read; the query was rejected before any registry access',
    status: 'denied',
    ts: '2026-06-21T12:04:15.000Z',
    request: {
      method: 'POST',
      url: 'solmara://citizen-portal/blocked-before-evidence',
      body: {
        requirement: 'urn:solmara:requirement:person-is-deceased:v1',
        purpose: 'pension-payment-review'
      }
    },
    response: {
      status: 403,
      body: {
        type: 'urn:solmara:portal:problem:not_authorized',
        title: 'Portal authorization denied the request',
        status: 403,
        detail: 'The portal stopped this request before source access'
      }
    }
  },

  // 5. Identity-binding (pinned to bottom as the foundation)
  {
    id: 'event-0',
    seq: 0,
    fieldId: 'identity',
    authority: 'civil',
    headline:
      'Identity bound via eSignet: session linked to 2300018263 (Elena Dela Cruz)',
    answered: 'Civil answered: identity = bound (eSignet UserInfo)',
    notDisclosed:
      'Only name and national ID were shared; no other civil facts disclosed',
    status: 'ok',
    ts: '2026-06-21T12:03:58.000Z',
    request: {
      method: 'POST',
      url: 'https://esignet.solmara.example/v1/userinfo',
      body: {
        claim: 'identity',
        purpose: 'session_binding',
        relationship: 'self'
      }
    },
    response: {
      status: 200,
      body: {
        sub: '2300018263',
        name: 'Elena Dela Cruz',
        source_authority: 'Civil Registry via eSignet',
        as_of: '2026-06-21'
      }
    },
    proof: {
      signedBy: 'No credential issued; eSignet UserInfo bound the portal session',
      algorithm: 'OIDC UserInfo response; no credential signature asserted',
      issuerKey: 'Not applicable for UserInfo',
      holderBound: 'Portal session bound to the configured UserInfo subject claim',
      credential: 'OIDC session identity, not a verifiable credential',
      auditId: 'session-binding:event-0'
    }
  }
];

// The identity-binding entry is always pinned to the bottom.
export const IDENTITY_TRACE_ID = 'event-0';
