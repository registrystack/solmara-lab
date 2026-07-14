import { PURPOSES } from '$lib/forms/descriptors';
import type { ScenarioResult } from '$lib/providers/mock/scenarios';

export type AuthorityClient =
  | 'craPension'
  | 'craCitizen'
  | 'niaCitizen'
  | 'sipfPension'
  | 'nagdi';

export type AuthorityPlan = {
  client: AuthorityClient;
  authority: string;
  serviceId: string;
  claimId: string;
  purpose: string;
  scheme?: string;
};

/**
 * Resolve the exact authority-owned claims used by a portal field. This is the
 * shared plan for live and mock providers, so the mock cannot present a
 * portal-composed decision as if one Notary produced it.
 */
export function authorityPlan(
  scenarioKey: string,
  scenario: ScenarioResult
): AuthorityPlan[] {
  const craPension: AuthorityPlan = {
    client: 'craPension',
    authority: 'Civil Registration Authority',
    serviceId: 'cra-notary',
    claimId: 'person-is-deceased',
    purpose: PURPOSES.pensionPaymentReview
  };
  const sipfPayment: AuthorityPlan = {
    client: 'sipfPension',
    authority: 'Social Insurance and Pensions Fund',
    serviceId: 'sipf-notary',
    claimId: 'pension-payment-active',
    purpose: PURPOSES.pensionPaymentReview
  };
  const sipfSurvivor: AuthorityPlan = {
    client: 'sipfPension',
    authority: 'Social Insurance and Pensions Fund',
    serviceId: 'sipf-notary',
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
        authority: 'Civil Registration Authority',
        serviceId: 'cra-notary',
        claimId: 'civil-record-linked',
        purpose: PURPOSES.citizenSelfService
      },
      {
        client: 'niaCitizen',
        authority: 'National Identity Agency',
        serviceId: 'nia-notary',
        claimId: 'citizen-population-record-active',
        purpose: PURPOSES.citizenSelfService
      }
    ];
  }
  if (scenario.service === 'nagdi') {
    return [
      {
        client: 'nagdi',
        authority: 'National Agricultural Data Institute',
        serviceId: 'nagdi-notary',
        claimId: scenario.claimId,
        purpose: scenario.purpose,
        scheme: 'farmer_id'
      }
    ];
  }
  if (scenario.notary === 'civil') return [craPension];
  if (scenario.service === 'pension') return [sipfSurvivor];
  throw new Error(`No authority route for scenario "${scenarioKey}"`);
}

export function isApplicationOwnedPlan(plan: AuthorityPlan[]): boolean {
  return plan.length > 1;
}
