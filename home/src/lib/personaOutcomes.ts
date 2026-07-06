import type { Persona } from './types';

export type PersonaOutcomeTone = 'positive' | 'refusal' | 'note';

export type PersonaOutcome = {
  storyId: string;
  storyTitle: string;
  stepId?: string;
  tone: PersonaOutcomeTone;
  text: string;
};

/**
 * What happens to each shown persona in the guided stories, keyed by
 * `Persona.roster_primary_id` (the same id the scenario modules under
 * `scenarios/*.py` evaluate as the request subject, and the id already used
 * for the portal handoff link). Every `storyId`/`stepId` pair here was read
 * directly off the scenario modules' `story()` step lists and subject maps;
 * `personaOutcomes.test.ts` cross-checks every entry against that set so a
 * renamed or removed step fails the test instead of silently drifting.
 *
 * Personas without a wired scenario step (household heads, guardians without
 * their own evaluation, and two world-bible-only livestock controls) are left
 * out of this table on purpose rather than given an invented outcome.
 */
const OUTCOMES: Record<string, PersonaOutcome[]> = {
  // Mateo Santos, child benefit positive child.
  '2300010248': [
    {
      storyId: 'birth-to-child-benefit',
      storyTitle: 'Birth to child benefit',
      stepId: 'positive',
      tone: 'positive',
      text: 'Reviewed for the child benefit and comes back eligible: every claim is met.'
    }
  ],
  // Elena Dela Cruz, Mateo's guardian and the citizen self-service positive subject.
  '2300018263': [
    {
      storyId: 'birth-to-child-benefit',
      storyTitle: 'Birth to child benefit',
      stepId: 'positive',
      tone: 'note',
      text: "Mateo's guardian: may preview his enrollment-eligibility credential once his review clears."
    },
    {
      storyId: 'citizen-self-service',
      storyTitle: 'Citizen self-service',
      stepId: 'positive',
      tone: 'positive',
      text: 'Signs into her own portal and previews her own minimized status summary, nothing else.'
    }
  ],
  // Hana Aquino, child benefit denied above threshold.
  '2300036523': [
    {
      storyId: 'birth-to-child-benefit',
      storyTitle: 'Birth to child benefit',
      stepId: 'poverty-control',
      tone: 'refusal',
      text: 'Refused: her household sits above the poverty threshold, exactly as designed.'
    }
  ],
  // Tomas Bello, child benefit denied duplicate enrollment.
  '2300054788': [
    {
      storyId: 'birth-to-child-benefit',
      storyTitle: 'Birth to child benefit',
      stepId: 'duplicate-control',
      tone: 'refusal',
      text: 'Refused: already enrolled, exactly as designed.'
    }
  ],
  // Karim Kone, birth registration gap: the inclusion path, not a dead end.
  '2300073046': [
    {
      storyId: 'birth-to-child-benefit',
      storyTitle: 'Birth to child benefit',
      stepId: 'unregistered-control',
      tone: 'note',
      text: 'No birth record found yet, so he is routed to register the birth first, not turned away.'
    }
  ],
  // Esteban Cruz, deceased child-benefit control.
  '2300091305': [
    {
      storyId: 'birth-to-child-benefit',
      storyTitle: 'Birth to child benefit',
      stepId: 'deceased-control',
      tone: 'refusal',
      text: 'Refused, exactly as designed: the eligibility check fails on life status alone.'
    }
  ],
  // Rafael Nkomo, pension positive deceased member: the payment stop is the intended outcome.
  '2300109568': [
    {
      storyId: 'death-to-pension-survivor',
      storyTitle: 'Death to pension stop plus survivor benefit',
      stepId: 'stop-payment',
      tone: 'positive',
      text: 'His pension stops: the death fact alone is enough, cause of death is never asked.'
    }
  ],
  // Imani Nkomo, survivor benefit positive spouse.
  '2300118698': [
    {
      storyId: 'death-to-pension-survivor',
      storyTitle: 'Death to pension stop plus survivor benefit',
      stepId: 'survivor-benefit',
      tone: 'positive',
      text: 'Eligible for the survivor benefit, linked to Rafael by marriage registration alone.'
    }
  ],
  // Otto Ferreira, pension stale-data failure: death not yet registered.
  '2300127827': [
    {
      storyId: 'death-to-pension-survivor',
      storyTitle: 'Death to pension stop plus survivor benefit',
      stepId: 'stale-control',
      tone: 'note',
      text: 'No death registered yet, so his pension keeps paying until the civil register catches up.'
    }
  ],
  // Mina Rahman, survivor denied: marriage dissolved.
  '2300146081': [
    {
      storyId: 'death-to-pension-survivor',
      storyTitle: 'Death to pension stop plus survivor benefit',
      stepId: 'dissolved-control',
      tone: 'refusal',
      text: 'Refused: the marriage was dissolved, exactly as designed.'
    }
  ],
  // Amina Kone, farmer voucher positive and livestock movement positive owner.
  'FR-1001': [
    {
      storyId: 'farmer-climate-smart-voucher',
      storyTitle: 'Farmer climate-smart voucher',
      stepId: 'positive',
      tone: 'positive',
      text: 'Qualifies for the climate-smart input voucher.'
    },
    {
      storyId: 'farmer-climate-smart-voucher',
      storyTitle: 'Farmer climate-smart voucher',
      stepId: 'movement-permit',
      tone: 'positive',
      text: 'Also clears the livestock movement permit, evaluated under its own purpose.'
    }
  ],
  // Diego Santos, farmer voucher denied: no data-use authorization on file.
  'FR-1002': [
    {
      storyId: 'farmer-climate-smart-voucher',
      storyTitle: 'Farmer climate-smart voucher',
      stepId: 'authorization-control',
      tone: 'refusal',
      text: 'Refused: no data-use authorization on file, exactly as designed.'
    }
  ]
};

/** Ordered showcase of `roster_primary_id`s: one positive subject or named control per guided story. */
const FEATURED_PERSONA_IDS = [
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

/** What will happen to this persona in the guided stories, or `[]` when no scenario step evaluates them. */
export function personaOutcomes(persona: Pick<Persona, 'roster_primary_id'>): PersonaOutcome[] {
  return OUTCOMES[persona.roster_primary_id] ?? [];
}

/** Deep link to the outcome's story, anchored to its step when the outcome names one. */
export function personaOutcomeHref(outcome: Pick<PersonaOutcome, 'storyId' | 'stepId'>): string {
  return outcome.stepId ? `/stories/${outcome.storyId}#${outcome.stepId}` : `/stories/${outcome.storyId}`;
}

/**
 * The curated cast shown on the Nation section: one positive subject or named
 * control per guided story (spec section 3), in showcase order. Personas
 * missing from the roster are skipped rather than throwing, so the section
 * degrades gracefully if the generator's cast ever changes.
 */
export function featuredPersonas(personas: Persona[]): Persona[] {
  const byId = new Map(personas.map((persona) => [persona.roster_primary_id, persona]));
  return FEATURED_PERSONA_IDS.map((id) => byId.get(id)).filter((persona): persona is Persona => Boolean(persona));
}
