import { describe, expect, it } from 'vitest';
import { buildCurlExamples } from './tokens';

describe('engineer curl examples', () => {
  it('uses distinct authority endpoints and JSON-body purposes', () => {
    const examples = buildCurlExamples();
    const commands = examples.map((example) => example.command).join('\n');

    expect(examples.map((example) => example.id)).toEqual([
      'metadata-get',
      'cra-evidence-post',
      'nia-evidence-post',
      'programme-post',
      'wrong-purpose-post'
    ]);
    expect(commands).toContain('cra-evidence.solmara.registrystack.org/v1/evidence');
    expect(commands).toContain('nia-evidence.solmara.registrystack.org/v1/evidence');
    expect(commands).toContain('"purpose":"https://id.registrystack.org/solmara/purpose/child-benefit-review"');
    expect(commands).toContain('"requirement":"https://id.registrystack.org/solmara/requirement/nia-child-benefit/v1"');
    expect(commands).not.toContain('/purpose/child-benefit-review/v1');
    expect(commands).not.toContain('Data-Purpose');
  });

  it('publishes placeholders, never token or subject values', () => {
    const commands = buildCurlExamples().map((example) => example.command).join('\n');
    expect(commands).toContain('$CRA_EVIDENCE_ACCESS_TOKEN');
    expect(commands).toContain('$SOLMARA_UIN');
    expect(commands).toContain('$REQUEST_NONCE');
    expect(commands).not.toMatch(/Bearer\s+(?!\$)[A-Za-z0-9._-]+/);
    expect(commands).not.toMatch(/\bFR-\d+\b|\b[2-9]\d{9}\b/);
  });
});
