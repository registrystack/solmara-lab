import type { ProofTrace } from '$lib/types';

export const CANNED_TRACES: ProofTrace[] = [
  {
    id: 'event-1',
    seq: 1,
    fieldId: 'farmer-registered',
    authority: 'agri',
    headline: 'Checking NAgDI for farmer registration status...',
    answered: 'National Agricultural Data Institute response is pending',
    notDisclosed: 'Only the reviewed answer is requested, no farm details',
    status: 'in_flight',
    ts: '2026-06-21T12:04:05.000Z',
    purpose: 'voucher-eligibility-review',
    resultState: 'in_flight',
    presentations: [
      {
        authority: 'National Agricultural Data Institute',
        issuer: 'did:web:id.registrystack.org:solmara:authority:nagdi',
        serviceId: 'nagdi-evidence',
        source: 'Relay lookup'
      }
    ]
  },
  {
    id: 'event-2',
    seq: 2,
    fieldId: 'farmer-registered',
    authority: 'agri',
    headline: 'Confirmed by NAgDI: the applicant did not have to prove this herself',
    answered: 'National Agricultural Data Institute answered: farmer-registered = true',
    notDisclosed: 'Only the yes/no answer, no farm details or parcel coordinates',
    status: 'ok',
    ts: '2026-06-21T12:04:09.000Z',
    purpose: 'voucher-eligibility-review',
    resultState: 'verified',
    responseStatus: 200,
    presentations: [
      {
        authority: 'National Agricultural Data Institute',
        issuer: 'did:web:id.registrystack.org:solmara:authority:nagdi',
        serviceId: 'nagdi-evidence',
        source: 'Relay lookup'
      }
    ],
    proof: {
      signedBy: 'National Agricultural Data Institute issued the returned Evidence',
      algorithm: 'Verified Evidence assertion',
      issuerKey: 'Authority Evidence JWKS',
      holderBound: 'Audience-scoped to the portal request',
      credential: 'Minimum-disclosure Evidence assertion'
    }
  },
  {
    id: 'event-3',
    seq: 3,
    fieldId: 'household-below-poverty-threshold',
    authority: 'socialRegistry',
    headline: 'The household is below the reviewed programme threshold',
    answered: 'Social Registry Office answered: household-below-poverty-threshold = true',
    notDisclosed: 'Predicate only, not poverty score or household roster',
    status: 'ok',
    ts: '2026-06-21T12:04:12.000Z',
    purpose: 'child-benefit-review',
    resultState: 'verified',
    responseStatus: 200,
    presentations: [
      {
        authority: 'Social Registry Office',
        issuer: 'did:web:id.registrystack.org:solmara:authority:sro',
        serviceId: 'sro-evidence',
        source: 'immutable extract'
      }
    ],
    proof: {
      signedBy: 'Social Registry Office issued the returned Evidence',
      algorithm: 'Verified Evidence assertion',
      issuerKey: 'Authority Evidence JWKS',
      holderBound: 'Audience-scoped to the portal request',
      credential: 'Minimum-disclosure Evidence assertion'
    }
  },
  {
    id: 'event-4',
    seq: 4,
    fieldId: 'person-is-deceased',
    headline: 'Denied by the portal: request was not authorized, no data read',
    answered: 'Portal authorization gate returned 403 not_authorized',
    notDisclosed: 'No source was contacted',
    status: 'denied',
    ts: '2026-06-21T12:04:15.000Z',
    purpose: 'pension-payment-review',
    resultState: 'error',
    responseStatus: 403,
    presentations: []
  },
  {
    id: 'event-0',
    seq: 0,
    fieldId: 'identity',
    headline: 'Identity bound through eSignet',
    answered: 'eSignet bound the signed-in portal session',
    notDisclosed: 'No additional identity attributes were shared',
    status: 'ok',
    ts: '2026-06-21T12:03:58.000Z',
    purpose: 'session-binding',
    resultState: 'prefilled',
    responseStatus: 200,
    presentations: []
  }
];

export const IDENTITY_TRACE_ID = 'event-0';
