import { describe, expect, it } from 'vitest';
import { featuredPersonas, personaOutcomeHref, personaOutcomes } from './personaOutcomes';
import type { Persona } from './types';

const KNOWN_STORY_STEPS: Record<string, string[]> = {
  'birth-to-child-benefit': [
    'discover',
    'positive',
    'deceased-control',
    'poverty-control',
    'unregistered-control',
    'duplicate-control',
    'purpose-denial'
  ],
  'death-to-pension-survivor': [
    'discover',
    'stop-payment',
    'survivor-benefit',
    'stale-control',
    'dissolved-control',
    'cause-of-death-denial'
  ],
  'farmer-climate-smart-voucher': [
    'discover',
    'positive',
    'authorization-control',
    'redeemed-control',
    'movement-permit',
    'purpose-denial'
  ],
  'citizen-self-service': ['discover', 'positive', 'purpose-denial']
};

function persona(overrides: Partial<Persona>): Persona {
  return {
    persona_id: 'x',
    roster_primary_id: 'x',
    given_name: 'Test',
    family_name: 'Persona',
    role: 'test role',
    district_code: 'XS-0101',
    ...overrides
  };
}

describe('personaOutcomes', () => {
  it('gives Mateo Santos his positive child-benefit outcome, linked to the story step', () => {
    const outcomes = personaOutcomes(persona({ roster_primary_id: '2300010248' }));
    expect(outcomes).toHaveLength(1);
    expect(outcomes[0].storyId).toBe('birth-to-child-benefit');
    expect(outcomes[0].stepId).toBe('positive');
    expect(outcomes[0].text.length).toBeGreaterThan(0);
    expect(personaOutcomeHref(outcomes[0])).toBe('/stories/birth-to-child-benefit#positive');
  });

  it('gives a named control persona a refusal-toned outcome', () => {
    const outcomes = personaOutcomes(persona({ roster_primary_id: '2300036523' }));
    expect(outcomes).toHaveLength(1);
    expect(outcomes[0].tone).toBe('refusal');
    expect(outcomes[0].text).toMatch(/Refused/);
  });

  it('gives a persona who appears in more than one story more than one outcome line', () => {
    const outcomes = personaOutcomes(persona({ roster_primary_id: 'FR-1001' }));
    expect(outcomes.length).toBeGreaterThanOrEqual(2);
    const stepIds = outcomes.map((outcome) => outcome.stepId);
    expect(stepIds).toContain('positive');
    expect(stepIds).toContain('movement-permit');
  });

  it('returns no outcomes for a persona id with no wired scenario step', () => {
    expect(personaOutcomes(persona({ roster_primary_id: 'not-a-real-id' }))).toEqual([]);
  });

  it('never references a story id or step id that does not exist in the scenario modules', () => {
    const rosterIds = [
      '2300010248',
      '2300018263',
      '2300036523',
      '2300054788',
      '2300073046',
      '2300091305',
      '2300109568',
      '2300118698',
      '2300127827',
      '2300146081',
      'FR-1001',
      'FR-1002'
    ];
    for (const rosterId of rosterIds) {
      for (const outcome of personaOutcomes(persona({ roster_primary_id: rosterId }))) {
        expect(Object.keys(KNOWN_STORY_STEPS)).toContain(outcome.storyId);
        if (outcome.stepId) {
          expect(KNOWN_STORY_STEPS[outcome.storyId]).toContain(outcome.stepId);
        }
        expect(['positive', 'refusal', 'note']).toContain(outcome.tone);
      }
    }
  });

  it('builds the href with a step anchor when a step id is present, and without one otherwise', () => {
    expect(personaOutcomeHref({ storyId: 'birth-to-child-benefit' })).toBe('/stories/birth-to-child-benefit');
    expect(personaOutcomeHref({ storyId: 'birth-to-child-benefit', stepId: 'positive' })).toBe(
      '/stories/birth-to-child-benefit#positive'
    );
  });
});

describe('featuredPersonas', () => {
  const roster: Persona[] = [
    persona({ roster_primary_id: '2300054788', given_name: 'Tomas', family_name: 'Bello' }),
    persona({ roster_primary_id: '2300010248', given_name: 'Mateo', family_name: 'Santos' }),
    persona({ roster_primary_id: '2300027390', given_name: 'Luis', family_name: 'Okafor' })
  ];

  it('orders the showcase by the curated list, not the source order', () => {
    const shown = featuredPersonas(roster);
    expect(shown.map((p) => p.roster_primary_id)[0]).toBe('2300010248');
  });

  it('drops curated ids that are absent from the roster instead of throwing', () => {
    const shown = featuredPersonas([persona({ roster_primary_id: '2300010248' })]);
    expect(shown).toHaveLength(1);
  });

  it('drops roster personas that are not on the curated showcase list', () => {
    const shown = featuredPersonas(roster);
    expect(shown.some((p) => p.roster_primary_id === '2300027390')).toBe(false);
  });
});
