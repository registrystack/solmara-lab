// The three wave 1 ServiceForm descriptors.
//
// Each Field maps a kind/claim/notary/purpose/disclose so the form page can drive
// the EvidenceField renderer and the BFF can resolve a canned scenario by field
// id. The field ids ARE the scenario lookup keys the MockEvidenceProvider expects
// (see resolveScenarioKey), so they must match the keys in providers/mock/scenarios.ts.
//
// Exactly ONE field across all three forms is the climax manual button: the
// pension-survivor survivor-benefit decision (manual: true). Child-benefit reads
// carry the `delegated` flag so the form gates them behind the consent step.

import type { Field, NotaryId, ServiceForm } from '$lib/types';

export const PURPOSES = {
  childBenefitReview: 'https://id.registrystack.org/solmara/purpose/child-benefit-review',
  pensionPaymentReview: 'https://id.registrystack.org/solmara/purpose/pension-payment-review',
  survivorBenefitDetermination: 'https://id.registrystack.org/solmara/purpose/survivor-benefit-determination',
  voucherEligibilityReview: 'https://id.registrystack.org/solmara/purpose/voucher-eligibility-review',
  citizenSelfService: 'https://id.registrystack.org/solmara/purpose/citizen-self-service'
} as const;

// ---------------------------------------------------------------------------
// farmer-voucher: the form fills itself from Agriculture, no delegation, no gate.
// ---------------------------------------------------------------------------
const agriSubsidy: ServiceForm = {
  slug: 'farmer-voucher',
  title: 'Farmer Climate-Smart Voucher',
  authorities: ['agri'],
  fields: [
    {
      id: 'agri-identity',
      label: 'Name and SolmaraID',
      kind: 'self',
      purpose: PURPOSES.voucherEligibilityReview
    },
    {
      id: 'registered-farmer',
      label: 'Registered farmer?',
      kind: 'verify',
      claim: 'farmer-registered',
      notary: 'agri',
      purpose: PURPOSES.voucherEligibilityReview,
      disclose: 'Not disclosed: only the yes/no, no farm details'
    },
    {
      id: 'farm-holding',
      label: 'Purpose authorization',
      kind: 'verify',
      claim: 'data-use-authorized-for-purpose',
      notary: 'agri',
      purpose: PURPOSES.voucherEligibilityReview,
      disclose: 'Not disclosed: unrelated farmer records or workbook rows'
    },
    {
      id: 'agri-requested-quantity',
      label: 'Requested input quantity',
      kind: 'self',
      selfPlaceholder: 'e.g. 4 bags of seed',
      purpose: PURPOSES.voucherEligibilityReview
    },
    {
      id: 'voucher-eligibility',
      label: 'Eligibility',
      kind: 'decision',
      claim: 'eligible-for-climate-smart-input-voucher',
      notary: 'agri',
      purpose: PURPOSES.voucherEligibilityReview,
      disclose: 'Not disclosed: the underlying parcel measurements behind the decision'
    }
  ]
};

// ---------------------------------------------------------------------------
// child-benefit: checks stay locked until consent locates the selected child.
// ---------------------------------------------------------------------------
const educationGrant: ServiceForm = {
  slug: 'child-benefit',
  title: 'Birth to Child Benefit',
  authorities: ['childCivil', 'population', 'socialRegistry', 'programme'],
  fields: [
    {
      id: 'child-benefit-consent',
      label: 'Consent',
      kind: 'self',
      purpose: PURPOSES.childBenefitReview
    },
    {
      id: 'birth-event-exists',
      label: 'Child birth registered',
      kind: 'verify',
      claim: 'birth-is-registered',
      notary: 'childCivil',
      purpose: PURPOSES.childBenefitReview,
      disclose: 'Not disclosed: place of birth and registration officer',
      delegated: { relationshipClaim: 'caregiver-link', dependentRef: 'selected-child' }
    },
    {
      id: 'population-record-active',
      label: 'Population record active',
      kind: 'verify',
      claim: 'population-record-active',
      notary: 'population',
      purpose: PURPOSES.childBenefitReview,
      disclose: 'Not disclosed: identity attributes or population register row',
      delegated: { relationshipClaim: 'caregiver-link', dependentRef: 'selected-child' }
    },
    {
      id: 'date-of-birth',
      label: 'Child age under 5',
      kind: 'verify',
      claim: 'child-age-under-5',
      notary: 'childCivil',
      purpose: PURPOSES.childBenefitReview,
      disclose: 'Not disclosed: full birth certificate or exact birth date',
      delegated: { relationshipClaim: 'caregiver-link', dependentRef: 'selected-child' }
    },
    {
      id: 'household-composition',
      label: 'Household below threshold',
      kind: 'verify',
      claim: 'household-below-poverty-threshold',
      notary: 'socialRegistry',
      purpose: PURPOSES.childBenefitReview,
      disclose: 'Not disclosed: poverty score or household roster',
      delegated: { relationshipClaim: 'caregiver-link', dependentRef: 'selected-child' }
    },
    {
      id: 'not-already-enrolled',
      label: 'Not already enrolled',
      kind: 'verify',
      claim: 'not-already-enrolled',
      notary: 'programme',
      purpose: PURPOSES.childBenefitReview,
      disclose: 'Not disclosed: other programme records',
      delegated: { relationshipClaim: 'caregiver-link', dependentRef: 'selected-child' }
    }
  ]
};

// ---------------------------------------------------------------------------
// pension-survivor: the multi-authority climax. The combined-eligibility decision is
// the single manual button across all four forms.
// ---------------------------------------------------------------------------
const socialCash: ServiceForm = {
  slug: 'pension-survivor',
  title: 'Pension Stop and Survivor Benefit',
  authorities: ['civil', 'social'],
  fields: [
    {
      id: 'person-is-alive',
      label: 'Death registration reviewed?',
      kind: 'verify',
      claim: 'person-is-deceased',
      notary: 'civil',
      purpose: PURPOSES.pensionPaymentReview,
      disclose: 'Not disclosed: any other civil record detail'
    },
    {
      id: 'disability-determination',
      label: 'Pension payment should stop?',
      kind: 'verify',
      claim: 'pension-payment-should-stop',
      notary: 'social',
      purpose: PURPOSES.pensionPaymentReview,
      disclose: 'Not disclosed: cause of death or other medical detail'
    },
    {
      id: 'functioning-assessment',
      label: 'Survivor relationship',
      kind: 'verify',
      claim: 'survivor-is-eligible',
      notary: 'social',
      purpose: PURPOSES.survivorBenefitDetermination,
      disclose: 'Not disclosed: the full marriage record'
    },
    {
      id: 'pension-payment-active',
      label: 'Pension payment active?',
      kind: 'verify',
      claim: 'pension-payment-active',
      notary: 'social',
      purpose: PURPOSES.pensionPaymentReview,
      disclose: 'Not disclosed: payment amount or payment history'
    },
    {
      id: 'social-requested-amount',
      label: 'Requested survivor benefit',
      kind: 'self',
      selfPlaceholder: 'e.g. 120 SOL / month',
      purpose: PURPOSES.pensionPaymentReview
    },
    {
      id: 'combined-support-eligibility',
      label: 'Eligibility decision',
      kind: 'decision',
      claim: 'survivor-benefit-eligible',
      notary: 'social',
      purpose: PURPOSES.survivorBenefitDetermination,
      disclose: 'Not disclosed: the raw inputs each authority used',
      manual: true
    }
  ]
};

// The catalog: ordered by the Solmara wave 1 story list.
export const FORMS: ServiceForm[] = [educationGrant, socialCash, agriSubsidy];

const FORMS_BY_SLUG: Record<string, ServiceForm> = Object.fromEntries(
  FORMS.map((f) => [f.slug, f])
) as Record<string, ServiceForm>;

export function getForm(slug: string): ServiceForm | undefined {
  return FORMS_BY_SLUG[slug];
}

// Catalog card copy. Kept beside the descriptors so the catalog and the form
// header read the same one-line summary.
export type CatalogEntry = {
  slug: string;
  title: string;
  summary: string;
  authorities: NotaryId[];
};

export const CATALOG: CatalogEntry[] = [
  {
    slug: 'child-benefit',
    title: educationGrant.title,
    summary: 'A grant for your child: read about someone else, only after a proven guardian link.',
    authorities: educationGrant.authorities
  },
  {
    slug: 'pension-survivor',
    title: socialCash.title,
    summary: 'Death registration and pension evidence decide stop-payment and survivor eligibility.',
    authorities: socialCash.authorities
  },
  {
    slug: 'farmer-voucher',
    title: agriSubsidy.title,
    summary: 'NAgDI evidence supports voucher eligibility without exporting workbooks.',
    authorities: agriSubsidy.authorities
  }
];

// Helper: which fields auto-fetch on mount (verify/fetch, plus a non-manual
// decision like the agri voucher, excluding the manual climax decision and the
// consent/self placeholders). A delegated field is gated by the form page until
// the guardian link resolves, so it is excluded from the initial concurrent burst.
export function autoFetchFields(form: ServiceForm): Field[] {
  return form.fields.filter(
    (f) =>
      (f.kind === 'verify' || f.kind === 'fetch' || f.kind === 'decision') &&
      !f.manual &&
      !f.delegated
  );
}

// Helper: the single manual decision field, if the form has one.
export function manualField(form: ServiceForm): Field | undefined {
  return form.fields.find((f) => f.manual === true);
}

// Helper: the delegated fields (the second hop), in order.
export function delegatedFields(form: ServiceForm): Field[] {
  return form.fields.filter((f) => f.delegated !== undefined);
}
