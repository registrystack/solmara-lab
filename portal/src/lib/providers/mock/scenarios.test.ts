import { describe, expect, it } from 'vitest';
import { AUTHORITY_LABEL, NOTARY_ISSUER_KEY, SCENARIOS } from './scenarios';

// The depth-1 proof feed always names the authority that actually signed the
// answer. Every "answered" line must open with that authority's canonical
// label (the same label the field badge, ministry rail, and proof crypto
// "signedBy" already use for that notary id), never an operational short
// name or nickname.
describe('SCENARIOS answered lines use the canonical authority label', () => {
  for (const [key, scenario] of Object.entries(SCENARIOS)) {
    const label = AUTHORITY_LABEL[scenario.notary];

    it(`"${key}" (notary: ${scenario.notary}) opens with "${label} answered:"`, () => {
      expect(scenario.answered.startsWith(`${label} answered:`)).toBe(true);
    });
  }
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
    for (const scenario of scenarios) {
      expect(NOTARY_ISSUER_KEY[scenario.notary]).toContain('child-benefit-notary');
      expect(NOTARY_ISSUER_KEY[scenario.notary]).not.toContain('notary:citizen');
    }
  });
});
