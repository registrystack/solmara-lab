import { describe, expect, it } from 'vitest';
import { buildCurlExamples, parsePublishedTokens, publishRequestTokens } from './tokens';

describe('published local application token allowlist', () => {
  it('renders only tokens explicitly named in the allowlist JSON', () => {
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-child","unknown":"tok-unknown"}');
    expect(tokens.map((token) => token.token)).toEqual(['tok-child', 'tok-unknown']);
    expect(tokens[0].purpose).toBe('child-benefit-review');
  });

  it('fails closed for absent or malformed allowlists', () => {
    expect(parsePublishedTokens(undefined)).toEqual([]);
    expect(parsePublishedTokens('not json')).toEqual([]);
    expect(parsePublishedTokens('[]')).toEqual([]);
  });

  it('builds metadata and child collector curls without exposing Mint credentials', () => {
    const examples = buildCurlExamples(parsePublishedTokens('{"child-benefit-federator":"tok-child"}'));
    expect(examples.map((example) => example.id)).toEqual([
      'metadata-get',
      'claims-get',
      'evaluate-post',
      'wrong-purpose-post'
    ]);
    expect(examples.find((example) => example.id === 'evaluate-post')?.command).toContain('tok-child');
    expect(examples.find((example) => example.id === 'wrong-purpose-post')?.command).toContain('pension-payment-review');
    expect(JSON.stringify(examples)).not.toContain('client-private.jwk');
  });

  it('republishes only the exact child collector token into matching request sources', () => {
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-child"}');
    const result = publishRequestTokens(
      {
        request_source: {
          method: 'POST',
          url: 'http://localhost:4321/v1/evaluations',
          headers: { 'x-api-key': '[runtime token hidden]', 'Data-Purpose': 'child-benefit-review' }
        },
        request_sources: [
          {
            method: 'POST',
            url: 'https://localhost:4341/v1/evidence',
            headers: { Authorization: 'Bearer [runtime token hidden]' },
            body: { purpose: 'child-benefit-review' }
          }
        ]
      },
      tokens
    );
    expect(result.request_source.headers['x-api-key']).toBe('tok-child');
    expect(result.request_sources[0].headers.Authorization).toBe('Bearer [runtime token hidden]');
  });
});
