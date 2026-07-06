import { describe, expect, it } from 'vitest';
import { assembleProblemCodes } from './problemcodes';
import type { Purpose, Scenario } from '$lib/types';

const purposes: Purpose[] = [
  {
    iri: 'https://id.registrystack.org/solmara/purpose/child-benefit-review',
    slug: 'child-benefit-review',
    advertisedBy: 'CRA',
    enforcedBy: 'child-benefit-notary',
    story: 'Birth to child benefit',
    denialCodes: ['pdp.purpose_not_permitted', 'federation.forbidden'],
    plainLanguage: 'permits child benefit evidence'
  }
];

const scenarios: Scenario[] = [
  {
    id: 'birth-to-child-benefit',
    title: 'Birth to child benefit',
    short_title: 'Child benefit',
    proves: '',
    domain: '',
    actor: '',
    intro: '',
    subject: { name: '', identifier: '' },
    requester: { name: '', purpose: '' },
    steps: [
      { id: 'positive', label: 'Evaluate', prompt: '', button: '', request_summary: '' },
      { id: 'purpose-denial', label: 'Purpose denial', prompt: '', button: '', request_summary: '' }
    ],
    receipt: []
  }
];

describe('problem-code assembly', () => {
  const codes = assembleProblemCodes(purposes, scenarios);

  it('includes every denial code from the catalogue plus the observed request.invalid', () => {
    const ids = codes.map((code) => code.code);
    expect(ids).toContain('pdp.purpose_not_permitted');
    expect(ids).toContain('federation.forbidden');
    expect(ids).toContain('request.invalid');
  });

  it('uses the problem type URI observed in real notary responses', () => {
    const pdp = codes.find((code) => code.code === 'pdp.purpose_not_permitted');
    expect(pdp?.typeUri).toBe('https://id.registrystack.org/problems/registry-notary/pdp/purpose_not_permitted');
    expect(pdp?.problemJson.status).toBe(403);
    expect(pdp?.problemJson.code).toBe('pdp.purpose_not_permitted');
  });

  it('links purpose_not_permitted to the story step that demonstrates it', () => {
    const pdp = codes.find((code) => code.code === 'pdp.purpose_not_permitted');
    expect(pdp?.demonstratedBy.map((link) => link.stepId)).toContain('purpose-denial');
    expect(pdp?.purposeSlugs).toContain('child-benefit-review');
  });

  it('anchors each code by its stable code string', () => {
    // Phase A deep-links to /problem-codes#pdp.purpose_not_permitted.
    expect(codes.some((code) => code.code === 'pdp.purpose_not_permitted')).toBe(true);
  });

  it('carries a coverage note for codes with no demonstrating story step', () => {
    const federation = codes.find((code) => code.code === 'federation.forbidden');
    expect(federation?.demonstratedBy).toHaveLength(0);
    expect(federation?.coverage).toBeTruthy();
  });
});
