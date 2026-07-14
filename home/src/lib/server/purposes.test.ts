import { describe, expect, it } from 'vitest';
import { buildPurposeViews, parsePurposes, readPurposes, storyLinksForPurpose } from './purposes';
import type { Scenario } from '$lib/types';

const SAMPLE = `# Solmara Purpose Catalogue

## Wave 1 Purposes

| Purpose IRI | Advertised by | Enforced by | Story | Denial problem codes |
|---|---|---|---|---|
| \`https://id.registrystack.org/solmara/purpose/child-benefit-review\` | CRA, NIA | \`child-benefit-federator\` plus source-owned child-benefit Notaries | Birth to child benefit | \`pdp.purpose_not_permitted\`; \`federation.forbidden\` for delegated calls |
| \`https://id.registrystack.org/solmara/purpose/voucher-eligibility-review\` | NAgDI | \`nagdi-notary\` | Farmer climate-smart voucher | \`pdp.purpose_not_permitted\` |

## Purpose Rules

\`child-benefit-review\` permits evidence needed to determine whether a child may
be enrolled in child support. It does not permit raw poverty scores.

\`voucher-eligibility-review\` permits NAgDI to evaluate farmer registration and
prior voucher status. It does not permit unrelated livestock movements.

## Credential And Offering Names

Ignore this section.
`;

function scenario(id: string, title: string, steps: { id: string; label: string; purpose: string }[]): Scenario {
  return {
    id,
    title,
    short_title: title,
    proves: '',
    domain: '',
    actor: '',
    intro: '',
    subject: { name: '', identifier: '' },
    requester: { name: '', purpose: '' },
    steps: steps.map((step) => ({
      id: step.id,
      label: step.label,
      prompt: '',
      button: '',
      request_summary: '',
      request_preview: { method: 'POST', url: 'http://x/v1/evaluations', headers: { 'Data-Purpose': step.purpose } }
    })),
    receipt: []
  };
}

describe('purposes parser', () => {
  it('parses both the table and the rule paragraph for each purpose', () => {
    const purposes = parsePurposes(SAMPLE);
    expect(purposes).toHaveLength(2);
    const child = purposes[0];
    expect(child.iri).toBe('https://id.registrystack.org/solmara/purpose/child-benefit-review');
    expect(child.slug).toBe('child-benefit-review');
    expect(child.advertisedBy).toBe('CRA, NIA');
    expect(child.enforcedBy).toBe('child-benefit-federator plus source-owned child-benefit Notaries');
    expect(child.story).toBe('Birth to child benefit');
    expect(child.denialCodes).toEqual(['pdp.purpose_not_permitted', 'federation.forbidden']);
    expect(child.plainLanguage).toContain('permits evidence needed to determine whether a child');
    expect(child.plainLanguage).toContain('does not permit raw poverty scores');
    // The rule paragraph must not leak markdown backticks.
    expect(child.plainLanguage).not.toContain('`');
  });

  it('does not treat the credential section as a rule paragraph', () => {
    const purposes = parsePurposes(SAMPLE);
    expect(purposes.every((purpose) => !purpose.plainLanguage.includes('Ignore this section'))).toBe(true);
  });

  it('reads the full normative catalogue with a plain-language paragraph per purpose', async () => {
    const purposes = await readPurposes();
    expect(purposes).toHaveLength(6);
    for (const purpose of purposes) {
      expect(purpose.slug.length).toBeGreaterThan(0);
      expect(purpose.plainLanguage.length).toBeGreaterThan(0);
    }
  });

  it('links purposes to the story steps that send them', () => {
    const scenarios = [
      scenario('birth-to-child-benefit', 'Birth to child benefit', [
        { id: 'positive', label: 'Evaluate eligible child', purpose: 'https://id.registrystack.org/solmara/purpose/child-benefit-review' },
        { id: 'purpose-denial', label: 'Purpose denial', purpose: 'https://id.registrystack.org/solmara/purpose/pension-payment-review' }
      ])
    ];
    const links = storyLinksForPurpose('https://id.registrystack.org/solmara/purpose/child-benefit-review', scenarios);
    expect(links).toHaveLength(1);
    expect(links[0]).toMatchObject({ storyId: 'birth-to-child-benefit', stepId: 'positive' });

    const views = buildPurposeViews(parsePurposes(SAMPLE), scenarios);
    expect(views[0].storyLinks).toHaveLength(1);
    expect(views[1].storyLinks).toHaveLength(0);
  });
});
