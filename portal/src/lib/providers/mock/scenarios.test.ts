import { describe, expect, it } from 'vitest';
import { AUTHORITY_LABEL, SCENARIOS } from './scenarios';

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
