import { describe, expect, it } from 'vitest';
import { assembleProblemCodes } from './problemcodes';
import type { Purpose, Scenario } from '$lib/types';

const purposes: Purpose[] = [
  {
    iri: 'child-benefit-review',
    slug: 'child-benefit-review',
    advertisedBy: 'CRA',
    enforcedBy: 'child-benefit-federator',
    story: 'Birth to child benefit',
    denialCodes: ['not_authorized'],
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

  it('includes current Evidence authorization and malformed-request codes', () => {
    const ids = codes.map((code) => code.code);
    expect(ids).toContain('not_authorized');
    expect(ids).toContain('malformed_request');
  });

  it('uses the current Registry Evidence problem type URI', () => {
    const pdp = codes.find((code) => code.code === 'not_authorized');
    expect(pdp?.typeUri).toBe('https://registrystack.org/problems/evidence/not_authorized');
    expect(pdp?.problemJson.status).toBe(403);
    expect(pdp?.problemJson.code).toBe('not_authorized');
  });

  it('links not_authorized to the story step that demonstrates it', () => {
    const pdp = codes.find((code) => code.code === 'not_authorized');
    expect(pdp?.demonstratedBy.map((link) => link.stepId)).toContain('purpose-denial');
    expect(pdp?.purposeSlugs).toContain('child-benefit-review');
  });

  it('anchors each code by its stable code string', () => {
    expect(codes.some((code) => code.code === 'not_authorized')).toBe(true);
  });
});
