import { PURPOSES } from '$lib/forms/descriptors';
import type { ScenarioResult } from '$lib/providers/mock/scenarios';
import type { AuthorityId } from '$lib/types';

export type AuthorityClient =
  | 'craPension'
  | 'craCitizen'
  | 'niaCitizen'
  | 'sipfPension'
  | 'nagdi';

export type AuthorityPlan = {
  client: AuthorityClient;
  authorityId: AuthorityId;
  authority: string;
  serviceId: string;
  claimId: string;
  purpose: string;
  scheme?: string;
};

/**
 * Resolve the exact authority-owned claims used by a portal field. This is the
 * shared plan for live and mock providers, so the mock cannot present a
 * portal-composed decision as if one Evidence service produced it.
 */
export function authorityPlan(
  scenarioKey: string,
  scenario: ScenarioResult
): AuthorityPlan[] {
  const craPension: AuthorityPlan = {
    client: 'craPension',
    authorityId: 'civil',
    authority: 'Civil Registration Authority',
    serviceId: 'registry-evidence',
    claimId: 'person-is-deceased',
    purpose: PURPOSES.pensionPaymentReview
  };
  const sipfPayment: AuthorityPlan = {
    client: 'sipfPension',
    authorityId: 'social',
    authority: 'Social Insurance and Pensions Fund',
    serviceId: 'registry-evidence',
    claimId: 'pension-payment-active',
    purpose: PURPOSES.pensionPaymentReview
  };
  const sipfSurvivor: AuthorityPlan = {
    client: 'sipfPension',
    authorityId: 'social',
    authority: 'Social Insurance and Pensions Fund',
    serviceId: 'registry-evidence',
    claimId: 'survivor-is-eligible',
    purpose: PURPOSES.survivorBenefitDetermination
  };

  if (scenarioKey === 'disability-determination') return [craPension, sipfPayment];
  if (scenarioKey === 'combined-support-eligibility') {
    return [craPension, sipfPayment, sipfSurvivor];
  }
  if (scenarioKey === 'pension-payment-active') return [sipfPayment];
  if (scenarioKey === 'functioning-assessment' || scenarioKey === 'stale') {
    return [sipfSurvivor];
  }
  if (scenarioKey === 'citizen-record-status') {
    return [
      {
        client: 'craCitizen',
        authorityId: 'civil',
        authority: 'Civil Registration Authority',
        serviceId: 'registry-evidence',
        claimId: 'civil-record-linked',
        purpose: PURPOSES.citizenSelfService
      },
      {
        client: 'niaCitizen',
        authorityId: 'population',
        authority: 'National Identity Agency',
        serviceId: 'registry-evidence',
        claimId: 'citizen-population-record-active',
        purpose: PURPOSES.citizenSelfService
      }
    ];
  }
  if (scenario.service === 'nagdi') {
    return [
      {
        client: 'nagdi',
        authorityId: 'agri',
        authority: 'National Agricultural Data Institute',
        serviceId: 'registry-evidence',
        claimId: scenario.claimId,
        purpose: scenario.purpose,
        scheme: 'farmer_id'
      }
    ];
  }
  if (scenario.authority === 'civil') return [craPension];
  if (scenario.service === 'pension') return [sipfSurvivor];
  throw new Error(`No authority route for scenario "${scenarioKey}"`);
}

export function isApplicationOwnedPlan(plan: AuthorityPlan[]): boolean {
  return plan.length > 1;
}
