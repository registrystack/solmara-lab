import { PURPOSES } from '$lib/forms/descriptors';
import type { ScenarioResult } from '$lib/providers/mock/scenarios';
import type { AuthorityId } from '$lib/types';
import { SOLMARA_AUTHORITIES } from '$lib/fields/authorities';

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
  source: 'immutable extract' | 'Relay lookup';
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
    serviceId: SOLMARA_AUTHORITIES.civil.serviceId,
    claimId: 'person-is-deceased',
    purpose: PURPOSES.pensionPaymentReview,
    source: 'Relay lookup'
  };
  const sipfPayment: AuthorityPlan = {
    client: 'sipfPension',
    authorityId: 'social',
    authority: 'Social Insurance and Pensions Fund',
    serviceId: SOLMARA_AUTHORITIES.social.serviceId,
    claimId: 'pension-payment-active',
    purpose: PURPOSES.pensionPaymentReview,
    source: 'Relay lookup'
  };
  const sipfSurvivor: AuthorityPlan = {
    client: 'sipfPension',
    authorityId: 'social',
    authority: 'Social Insurance and Pensions Fund',
    serviceId: SOLMARA_AUTHORITIES.social.serviceId,
    claimId: 'survivor-is-eligible',
    purpose: PURPOSES.survivorBenefitDetermination,
    source: 'Relay lookup'
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
        serviceId: SOLMARA_AUTHORITIES.civil.serviceId,
        claimId: 'civil-record-linked',
        purpose: PURPOSES.citizenSelfService,
        source: 'Relay lookup'
      },
      {
        client: 'niaCitizen',
        authorityId: 'population',
        authority: 'National Identity Agency',
        serviceId: SOLMARA_AUTHORITIES.population.serviceId,
        claimId: 'citizen-population-record-active',
        purpose: PURPOSES.citizenSelfService,
        source: 'immutable extract'
      }
    ];
  }
  if (scenario.service === 'nagdi') {
    return [
      {
        client: 'nagdi',
        authorityId: 'agri',
        authority: 'National Agricultural Data Institute',
        serviceId: SOLMARA_AUTHORITIES.agri.serviceId,
        claimId: scenario.claimId,
        purpose: scenario.purpose,
        source: 'Relay lookup',
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
