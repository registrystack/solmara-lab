// Canned scenarios driving the Phase 0 mock. Each scenario is keyed by a stable
// lookup id (field id, with a few delegated/denial variants) and carries enough
// to build both a ClaimResult and a ProofTrace whose depth-2 request/response
// bodies are STRUCTURALLY identical to the real Notary POST /v1/evaluations
// (EvaluateRequest / EvaluationResponse from registry-notary.openapi.json).
//
// Volatile fields (evaluation_id, issued_at/expires_at, signatures, freshness)
// are present but value-variable: they are stamped at evaluate() time, never
// byte-matched. Everything else (key set, types, ordering) matches the OpenAPI.

import type { FieldState, NotaryId, ProofStatus } from '$lib/types';
import { SOLMARA_AUTHORITIES } from '$lib/fields/authorities';
import { PURPOSES } from '$lib/forms/descriptors';

// Map a portal NotaryId to the human authority label the Notary returns and the
// proof inspector shows. Single canonical name per authority.
export const AUTHORITY_LABEL: Record<NotaryId, string> = {
  civil: SOLMARA_AUTHORITIES.civil.label,
  social: SOLMARA_AUTHORITIES.social.label,
  agri: SOLMARA_AUTHORITIES.agri.label,
  certs: SOLMARA_AUTHORITIES.certs.label
};

// Per-notary service id that appears in provenance.generated_by.service_id.
export const NOTARY_SERVICE_ID: Record<NotaryId, string> = {
  civil: SOLMARA_AUTHORITIES.civil.serviceId,
  social: SOLMARA_AUTHORITIES.social.serviceId,
  agri: SOLMARA_AUTHORITIES.agri.serviceId,
  certs: SOLMARA_AUTHORITIES.certs.serviceId
};

// Per-notary public DID and signing key id (did:web), depth-3 crypto.
export const NOTARY_ISSUER_KEY: Record<NotaryId, string> = {
  civil: SOLMARA_AUTHORITIES.civil.issuerKey,
  social: SOLMARA_AUTHORITIES.social.issuerKey,
  agri: SOLMARA_AUTHORITIES.agri.issuerKey,
  certs: SOLMARA_AUTHORITIES.certs.issuerKey
};

// What the Notary sends back as source_authority / the proof "answered" line.
// The `disclosure` mirrors the EvaluateRequest.disclosure on the wire.
export type ScenarioDisclosure = 'predicate' | 'value' | 'object' | 'decision';

// The depth-2 response value (the ClaimResultView.value). The runtime may return
// any JSON value; we keep it as unknown so booleans, dates, and objects all fit.
export type ScenarioResult = {
  // ---- routing / lookup ----
  notary: NotaryId;
  service: 'childBenefit' | 'pension' | 'nagdi' | 'citizen';
  claimId: string; // the wire claim id, e.g. 'farmer-registered'
  claimVersion: string;
  subjectPersona?: PersonaKey;
  // ---- request shaping (EvaluateRequest) ----
  purpose: string; // declared purpose
  disclosure: ScenarioDisclosure;
  // delegated scenarios send on_behalf_of + relationship:guardian, and read a
  // dependent subject. Non-delegated scenarios are relationship:self.
  delegated?: boolean;
  // ---- response / claim-result shaping (ClaimResultView) ----
  value: unknown; // boolean | string (date) | object summary
  satisfied: boolean | null; // null for plain value/object fetches
  subjectType: string; // 'person' | 'household' | 'holding'
  freshnessDays: number; // expires_at - issued_at, in days
  asOf: string; // human freshness date shown depth 1 (variable, demo-stable)
  // ---- portal-facing projection ----
  state: FieldState; // resulting FieldState
  display: string; // the value/predicate sentence shown in the field
  reasonCode?: string; // e.g. 'VR-RED-02'
  reasonCodes?: { code: string; authority: NotaryId; text: string }[]; // decisions
  // ---- proof depth-1 copy ----
  headline: string; // consequence-first
  answered: string; // "{Authority} answered: {claim} = {value}"
  notDisclosed: string; // ALWAYS present
  status: ProofStatus;
  // ---- denial / error shaping ----
  httpStatus: number; // 200 normally; 403 denial; 503 error
  denial?: { code: string; message: string }; // for the subject_mismatch beat
  // ---- resilience flavor ----
  // latencyMs is the deterministic delay; staggerOrder gives the top-to-bottom
  // stagger so fields land in a believable cascade, never all at once.
  latencyMs: number;
  staggerOrder: number;
  // an error scenario performs NO source read (used.source_count = 0)
  sourceCount: number;
};

type PersonaKey = 'elena' | 'mateo' | 'hana' | 'karim' | 'rafael' | 'aminaFarmer';

// Persona ids (already reconciled to real fixtures). These are SUBJECTS the BFF
// binds server-side; they NEVER reach the redacted proof feed. They live here so
// the mock can shape a realistic (then redacted) request.
export const PERSONA = {
  elena: '2300018263',
  mateo: '2300010248',
  hana: '2300036523',
  karim: '2300073046',
  rafael: '2300109568',
  aminaFarmer: 'FR-1001'
} as const;

// The canonical scenario table. Keys are the lookup ids the provider resolves a
// Field/ctx to (see resolveScenarioKey in index.ts).
export const SCENARIOS: Record<string, ScenarioResult> = {
  // ---------------------------------------------------------------------------
  // farmer-voucher
  // ---------------------------------------------------------------------------
  'registered-farmer': {
    notary: 'agri',
    service: 'nagdi',
    claimId: 'farmer-registered',
    claimVersion: '2026-07',
    subjectPersona: 'aminaFarmer',
    purpose: PURPOSES.voucherEligibilityReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 30,
    asOf: '2026-05-01',
    state: 'verified',
    display: 'Registered farmer: yes',
    headline: 'Confirmed by NAgDI, Amina did not have to prove this herself',
    answered: 'National Agricultural Data Institute answered: farmer-registered = true',
    notDisclosed: 'Not disclosed: only the yes/no, no farm details',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 900,
    staggerOrder: 0,
    sourceCount: 1
  },
  'farm-holding': {
    notary: 'agri',
    service: 'nagdi',
    claimId: 'data-use-authorized-for-purpose',
    claimVersion: '2026-07',
    subjectPersona: 'aminaFarmer',
    purpose: PURPOSES.voucherEligibilityReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'farmer',
    freshnessDays: 90,
    asOf: '2026-04-18',
    state: 'verified',
    display: 'Purpose authorization: yes',
    headline: 'Confirmed by NAgDI, the purpose is authorized for this service',
    answered: 'National Agricultural Data Institute answered: data-use-authorized-for-purpose = true',
    notDisclosed: 'Not disclosed: unrelated farmer records or workbook rows',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1400,
    staggerOrder: 1,
    sourceCount: 1
  },
  'voucher-eligibility': {
    notary: 'agri',
    service: 'nagdi',
    claimId: 'eligible-for-climate-smart-input-voucher',
    claimVersion: '2026-07',
    subjectPersona: 'aminaFarmer',
    purpose: PURPOSES.voucherEligibilityReview,
    disclosure: 'decision',
    value: { eligible: true, voucher_tier: 'standard' },
    satisfied: true,
    subjectType: 'farmer',
    freshnessDays: 7,
    asOf: '2026-05-20',
    state: 'verified',
    display: 'Eligible (standard voucher)',
    reasonCodes: [
      { code: 'AG-VCH-01', authority: 'agri', text: 'Registered-farmer status confirmed' },
      { code: 'AG-VCH-04', authority: 'agri', text: 'Holding under the 4 ha smallholder ceiling' }
    ],
    headline: 'Decided by Agriculture, eligibility signed with its reasons',
    answered: 'National Agricultural Data Institute answered: eligible-for-climate-smart-input-voucher = eligible',
    notDisclosed: 'Not disclosed: the underlying parcel measurements behind the decision',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1700,
    staggerOrder: 2,
    sourceCount: 1
  },

  // ---------------------------------------------------------------------------
  // child-benefit (delegated two-hop: social guardian-link, THEN civil reads)
  // ---------------------------------------------------------------------------
  'caregiver-link': {
    notary: 'civil',
    service: 'childBenefit',
    claimId: 'birth-is-registered',
    claimVersion: '2026-07',
    subjectPersona: 'mateo',
    purpose: PURPOSES.childBenefitReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 30,
    asOf: '2026-05-10',
    state: 'verified',
    display: 'Child record located',
    headline: 'Confirmed by Civil Registry, the selected child can be evaluated',
    answered: 'Civil Registry answered: birth-is-registered = true',
    notDisclosed: 'Not disclosed: any other civil record detail',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1100,
    staggerOrder: 0,
    sourceCount: 1
  },
  // The Civil reads below are HOP TWO: they are only authorized after the social
  // caregiver-link verify above succeeds. The provider enforces this gate.
  'birth-event-exists': {
    notary: 'civil',
    service: 'childBenefit',
    claimId: 'birth-is-registered',
    claimVersion: '2026-07',
    subjectPersona: 'mateo',
    purpose: PURPOSES.childBenefitReview,
    disclosure: 'predicate',
    delegated: true,
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 365,
    asOf: '2026-01-15',
    state: 'verified',
    display: 'Birth registered: yes',
    headline: 'Confirmed by Civil Registry, released only after the guardian link was proven',
    answered: 'Civil Registry answered: birth-is-registered = true',
    notDisclosed: 'Not disclosed: place of birth and registration officer',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1300,
    staggerOrder: 1,
    sourceCount: 1
  },
  'date-of-birth': {
    notary: 'civil',
    service: 'childBenefit',
    claimId: 'child-age-under-5',
    claimVersion: '2026-07',
    subjectPersona: 'mateo',
    purpose: PURPOSES.childBenefitReview,
    disclosure: 'predicate',
    delegated: true,
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 365,
    asOf: '2026-01-15',
    state: 'verified',
    display: 'Child age under 5: yes',
    headline: 'Confirmed by Civil Registry, released only after the guardian link was proven',
    answered: 'Civil Registry answered: child-age-under-5 = true',
    notDisclosed: 'Not disclosed: full birth certificate or exact birth date',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1500,
    staggerOrder: 2,
    sourceCount: 1
  },
  'household-composition': {
    notary: 'social',
    service: 'childBenefit',
    claimId: 'household-below-poverty-threshold',
    claimVersion: '2026-07',
    subjectPersona: 'mateo',
    purpose: PURPOSES.childBenefitReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'household',
    freshnessDays: 30,
    asOf: '2026-05-09',
    state: 'verified',
    display: 'Household below threshold: yes',
    headline: 'Fetched from Social Protection, size only',
    answered: 'Social Protection answered: household-below-poverty-threshold = true',
    notDisclosed: 'Not disclosed: poverty score or household roster',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1200,
    staggerOrder: 3,
    sourceCount: 1
  },
  'not-already-enrolled': {
    notary: 'social',
    service: 'childBenefit',
    claimId: 'not-already-enrolled',
    claimVersion: '2026-07',
    subjectPersona: 'mateo',
    purpose: PURPOSES.childBenefitReview,
    disclosure: 'predicate',
    delegated: true,
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 30,
    asOf: '2026-06-15',
    state: 'verified',
    display: 'Not already enrolled: yes',
    headline: 'Confirmed by MoSD programme MIS, no duplicate child-benefit enrollment',
    answered: 'MoSD programme MIS answered: not-already-enrolled = true',
    notDisclosed: 'Not disclosed: other programme records',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1250,
    staggerOrder: 4,
    sourceCount: 1
  },
  'eligible-for-child-benefit': {
    notary: 'social',
    service: 'childBenefit',
    claimId: 'eligible-for-child-benefit',
    claimVersion: '2026-07',
    subjectPersona: 'mateo',
    purpose: PURPOSES.childBenefitReview,
    disclosure: 'decision',
    delegated: true,
    value: { eligible: true, benefit: 'child-benefit' },
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 7,
    asOf: '2026-07-04',
    state: 'verified',
    display: 'Eligible for child benefit',
    reasonCodes: [
      { code: 'CRA-BRN-01', authority: 'civil', text: 'Birth registration confirmed' },
      { code: 'MOSD-PMT-01', authority: 'social', text: 'Household is in the priority band' },
      { code: 'MOSD-MIS-01', authority: 'social', text: 'No duplicate enrollment found' }
    ],
    headline: 'Decided by child-benefit Notary from minimized cross-registry predicates',
    answered: 'Child Benefit Notary answered: eligible-for-child-benefit = true',
    notDisclosed: 'Not disclosed: raw source rows behind the decision',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1500,
    staggerOrder: 5,
    sourceCount: 4
  },

  // ---------------------------------------------------------------------------
  // pension-survivor (multi-authority decision)
  // ---------------------------------------------------------------------------
  'person-is-alive': {
    notary: 'civil',
    service: 'pension',
    claimId: 'person-is-deceased',
    claimVersion: '2026-07',
    subjectPersona: 'rafael',
    purpose: PURPOSES.pensionPaymentReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 1,
    asOf: '2026-06-21',
    state: 'verified',
    display: 'Death registered: yes',
    headline: 'Confirmed by Civil Registry, death registration checked at source',
    answered: 'Civil Registry answered: person-is-deceased = true',
    notDisclosed: 'Not disclosed: any other civil record detail',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 800,
    staggerOrder: 0,
    sourceCount: 1
  },
  'disability-determination': {
    notary: 'social',
    service: 'pension',
    claimId: 'pension-payment-should-stop',
    claimVersion: '2026-07',
    subjectPersona: 'rafael',
    purpose: PURPOSES.pensionPaymentReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'pension_case',
    freshnessDays: 30,
    asOf: '2026-05-02',
    state: 'verified',
    display: 'Pension payment should stop: yes',
    headline: 'Confirmed by SIPF, active payment can be stopped',
    answered: 'SIPF answered: pension-payment-should-stop = true',
    notDisclosed: 'Not disclosed: payment amount or cause of death',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1000,
    staggerOrder: 1,
    sourceCount: 1
  },
  'functioning-assessment': {
    notary: 'social',
    service: 'pension',
    claimId: 'survivor-is-eligible',
    claimVersion: '2026-07',
    subjectPersona: 'rafael',
    purpose: PURPOSES.pensionPaymentReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 90,
    asOf: '2026-03-15',
    state: 'verified',
    display: 'Survivor eligible: yes',
    headline: 'Confirmed by SIPF, survivor eligibility is signed as a predicate',
    answered: 'SIPF answered: survivor-is-eligible = true',
    notDisclosed: 'Not disclosed: full marriage or pension case record',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1350,
    staggerOrder: 2,
    sourceCount: 1
  },
  'household-size': {
    notary: 'social',
    service: 'pension',
    claimId: 'survivor-is-eligible',
    claimVersion: '2026-07',
    subjectPersona: 'rafael',
    purpose: PURPOSES.pensionPaymentReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 30,
    asOf: '2026-05-09',
    state: 'verified',
    display: 'Beneficiary conflict check: clear',
    headline: 'Confirmed by SIPF, no conflicting survivor payment is active',
    answered: 'SIPF answered: survivor-is-eligible = true',
    notDisclosed: 'Not disclosed: other programme payment history',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1250,
    staggerOrder: 3,
    sourceCount: 1
  },
  'combined-support-eligibility': {
    notary: 'social',
    service: 'pension',
    claimId: 'survivor-is-eligible',
    claimVersion: '2026-07',
    subjectPersona: 'rafael',
    purpose: PURPOSES.survivorBenefitDetermination,
    disclosure: 'decision',
    value: { eligible: true, support_band: 'B' },
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 7,
    asOf: '2026-06-21',
    state: 'verified',
    display: 'Eligible (support band B)',
    reasonCodes: [
      { code: 'CIV-DRN-01', authority: 'civil', text: 'Death registration confirmed' },
      { code: 'SIPF-PAY-02', authority: 'social', text: 'Active pension payment should stop' },
      { code: 'SIPF-SUR-01', authority: 'social', text: 'Survivor relationship is eligible' }
    ],
    headline: 'Sealed by 3 authorities, no central data lake',
    answered: 'SIPF answered: survivor-is-eligible = true',
    notDisclosed: 'Not disclosed: the raw inputs each authority used',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 2100,
    staggerOrder: 4,
    sourceCount: 3
  },

  // ---------------------------------------------------------------------------
  // citizen self-service gallery fixture
  // ---------------------------------------------------------------------------
  'certificate-summary': {
    notary: 'certs',
    service: 'citizen',
    claimId: 'citizen-self-service-summary',
    claimVersion: '2026-07',
    subjectPersona: 'elena',
    purpose: PURPOSES.citizenSelfService,
    disclosure: 'object',
    value: {
      certificate_type: 'birth',
      certificate_id: 'CSR-BIRTH-2001',
      issued_on: '2001-03-12',
      registry_office: 'Solmara Central Civil Registry'
    },
    satisfied: null,
    subjectType: 'person',
    freshnessDays: 365,
    asOf: '2026-06-01',
    state: 'fetched',
    display: 'Birth certificate summary (CSR-BIRTH-2001)',
    headline: 'Fetched from Civil Registry as a signed certificate summary',
    answered: 'Citizen Notary answered: citizen-self-service-summary = CSR-BIRTH-2001',
    notDisclosed: 'Not disclosed: scanned certificate image and witness signatures',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1600,
    staggerOrder: 0,
    sourceCount: 1
  },

  // ---------------------------------------------------------------------------
  // Denial beat (cross-person, stranger Karim 2300073046): a real denied
  // evaluation, 403 subject_mismatch, NO source read.
  // ---------------------------------------------------------------------------
  denial: {
    notary: 'civil',
    service: 'pension',
    claimId: 'person-is-deceased',
    claimVersion: '2026-07',
    subjectPersona: 'karim',
    purpose: PURPOSES.pensionPaymentReview,
    disclosure: 'predicate',
    value: null,
    satisfied: null,
    subjectType: 'person',
    freshnessDays: 0,
    asOf: '2026-06-21',
    state: 'error',
    display: 'Denied: you cannot query this person',
    reasonCode: 'subject_mismatch',
    headline: 'Denied by Civil Registry before any record was read',
    answered: 'Civil Registry answered: 403 subject_mismatch, no data returned',
    notDisclosed: 'Not disclosed: nothing, the boundary held and no source was read',
    status: 'denied',
    httpStatus: 403,
    denial: { code: 'subject_mismatch', message: 'requester is not authorized for this target' },
    latencyMs: 600,
    staggerOrder: 0,
    sourceCount: 0
  },

  // ---------------------------------------------------------------------------
  // Resilience states (drive the degradation UX)
  // ---------------------------------------------------------------------------
  // SLOW: a still-in-flight live call that crosses the ~6-8s SLOW threshold but
  // eventually resolves verified. The provider surfaces SLOW before VERIFIED.
  slow: {
    notary: 'agri',
    service: 'nagdi',
    claimId: 'farmer-registered',
    claimVersion: '2026-07',
    subjectPersona: 'aminaFarmer',
    purpose: PURPOSES.voucherEligibilityReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: 30,
    asOf: '2026-05-01',
    state: 'verified',
    display: 'Registered farmer: yes',
    headline: 'Confirmed by Agriculture after a slow but live call',
    answered: 'National Agricultural Data Institute answered: farmer-registered = true',
    notDisclosed: 'Not disclosed: only the yes/no, no farm details',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 7000,
    staggerOrder: 0,
    sourceCount: 1
  },
  // ERROR: a hard failure (503). Scoped to the field, framed as minimization. No
  // source read, no value.
  error: {
    notary: 'social',
    service: 'childBenefit',
    claimId: 'household-below-poverty-threshold',
    claimVersion: '2026-07',
    subjectPersona: 'mateo',
    purpose: PURPOSES.childBenefitReview,
    disclosure: 'predicate',
    value: null,
    satisfied: null,
    subjectType: 'household',
    freshnessDays: 0,
    asOf: '2026-06-21',
    state: 'error',
    display: 'Could not reach Social Protection; other evidence is unaffected',
    reasonCode: 'upstream_unavailable',
    headline: 'Could not reach Social Protection, the other authorities are unaffected',
    answered: 'Social Protection answered: 503, no data returned',
    notDisclosed: 'Not disclosed: nothing, there is no central lake so this failure is isolated',
    status: 'error',
    httpStatus: 503,
    latencyMs: 8000,
    staggerOrder: 0,
    sourceCount: 0
  },
  // STALE: fetched but older than the freshness rule (BLUE + AMBER flag).
  stale: {
    notary: 'social',
    service: 'pension',
    claimId: 'survivor-is-eligible',
    claimVersion: '2026-07',
    subjectPersona: 'rafael',
    purpose: PURPOSES.pensionPaymentReview,
    disclosure: 'predicate',
    value: true,
    satisfied: true,
    subjectType: 'person',
    freshnessDays: -120, // expired: expires_at is in the past relative to issued
    asOf: '2025-09-30',
    state: 'stale',
    display: 'Survivor eligibility is stale and needs refresh',
    headline: 'Fetched from SIPF, but older than the freshness rule',
    answered: 'SIPF answered: survivor-is-eligible = true (stale)',
    notDisclosed: 'Not disclosed: the full pension case record',
    status: 'ok',
    httpStatus: 200,
    latencyMs: 1300,
    staggerOrder: 0,
    sourceCount: 1
  },
  // AMBIGUOUS: more than one record matched; never collapses to false.
  ambiguous: {
    notary: 'civil',
    service: 'pension',
    claimId: 'person-is-deceased',
    claimVersion: '2026-07',
    subjectPersona: 'rafael',
    purpose: PURPOSES.pensionPaymentReview,
    disclosure: 'predicate',
    value: null,
    satisfied: null,
    subjectType: 'person',
    freshnessDays: 0,
    asOf: '2026-06-21',
    state: 'ambiguous',
    display: 'More than one record matched; needs disambiguation',
    reasonCode: 'multiple_matches',
    headline: 'Civil Registry found more than one matching record',
    answered: 'Civil Registry answered: 2 candidate records, no single match',
    notDisclosed: 'Not disclosed: the candidate records themselves, only the count',
    status: 'error',
    httpStatus: 200,
    latencyMs: 1400,
    staggerOrder: 0,
    sourceCount: 2
  }
};

export type ScenarioKey = keyof typeof SCENARIOS;
