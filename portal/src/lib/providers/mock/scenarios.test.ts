import { describe, expect, it } from 'vitest';
import { AUTHORITY_LABEL, NOTARY_SERVICE_ID, SCENARIOS } from './scenarios';

// The depth-1 proof feed always names the authority that answered. Every
// "answered" line must open with that authority's canonical
// label (the same label the field badge, ministry rail, and proof crypto
// "signedBy" already use for that notary id), never an operational short
// name or nickname.
describe('SCENARIOS answered lines use the canonical authority label', () => {
  for (const [key, scenario] of Object.entries(SCENARIOS)) {
    const label = AUTHORITY_LABEL[scenario.notary];

    it(`"${key}" attributes its answered line to its actual owner`, () => {
      expect(
        scenario.answered.startsWith(
          scenario.applicationOwned ? 'Portal application answered:' : `${label} answered:`
        )
      ).toBe(true);
    });
  }
});

describe('pension purpose ownership', () => {
  it('uses survivor-benefit-determination for the survivor relationship source claim', () => {
    expect(SCENARIOS['functioning-assessment'].purpose).toContain(
      'survivor-benefit-determination'
    );
    expect(SCENARIOS['stale'].purpose).toBe(SCENARIOS['functioning-assessment'].purpose);
  });
});

describe('child-benefit source ownership', () => {
  it('uses five predicates from four source-owned Notaries without a composed eligibility scenario', () => {
    const scenarios = [
      SCENARIOS['birth-event-exists'],
      SCENARIOS['population-record-active'],
      SCENARIOS['date-of-birth'],
      SCENARIOS['household-composition'],
      SCENARIOS['not-already-enrolled']
    ];

    expect(scenarios.map((scenario) => scenario.claimId)).toEqual([
      'birth-is-registered',
      'population-record-active',
      'child-age-under-5',
      'household-below-poverty-threshold',
      'not-already-enrolled'
    ]);
    expect(new Set(scenarios.map((scenario) => scenario.notary))).toEqual(
      new Set(['childCivil', 'population', 'socialRegistry', 'programme'])
    );
    expect(SCENARIOS['eligible-for-child-benefit']).toBeUndefined();
    expect(scenarios.map((scenario) => NOTARY_SERVICE_ID[scenario.notary])).toEqual([
      'cra-notary',
      'nia-notary',
      'cra-notary',
      'sro-notary',
      'programme-notary'
    ]);
  });
});
