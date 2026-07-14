import { describe, expect, it } from 'vitest';
import { buildCurlExamples, parsePublishedTokens, publishRequestTokens } from './tokens';

describe('published-token allowlist', () => {
  it('renders only the tokens named in the allowlist JSON', () => {
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-child","pension-notary":"tok-pension"}');
    expect(tokens.map((token) => token.name)).toEqual(['child-benefit-federator', 'pension-notary']);
    expect(tokens.map((token) => token.token)).toEqual(['tok-child', 'tok-pension']);
  });

  it('never surfaces a token that is not a value in the allowlist', () => {
    // A container may hold many notary tokens; only those explicitly listed in
    // HOME_PUBLISHED_TOKENS may ever reach page data.
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-published"}');
    const serialised = JSON.stringify(tokens);
    expect(serialised).toContain('tok-published');
    expect(serialised).not.toContain('tok-secret-not-published');
  });

  it('does not fall back to any other environment variable', () => {
    // With no allowlist provided, no token is ever produced, even if individual
    // *_NOTARY_TOKEN variables exist in the environment.
    expect(parsePublishedTokens(undefined)).toEqual([]);
    expect(parsePublishedTokens('')).toEqual([]);
  });

  it('returns an empty list for a malformed allowlist rather than throwing', () => {
    expect(parsePublishedTokens('not json')).toEqual([]);
    expect(parsePublishedTokens('[]')).toEqual([]);
    expect(parsePublishedTokens('{"empty":""}')).toEqual([]);
  });

  it('builds four curl examples including the skeptic wrong-purpose call', () => {
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-child"}');
    const examples = buildCurlExamples(tokens);
    expect(examples.map((example) => example.id)).toEqual([
      'metadata-get',
      'claims-get',
      'evaluate-post',
      'wrong-purpose-post'
    ]);
    const wrong = examples.find((example) => example.id === 'wrong-purpose-post');
    expect(wrong?.command).toContain('pension-payment-review');
    // The published token is inlined into the authenticated examples.
    expect(examples.find((example) => example.id === 'claims-get')?.command).toContain('tok-child');
    // The unauthenticated metadata example never carries a token.
    expect(examples.find((example) => example.id === 'metadata-get')?.command).not.toContain('tok-child');
  });

  it('uses an env-var placeholder in curls when no child token is published', () => {
    const examples = buildCurlExamples([]);
    expect(examples.find((example) => example.id === 'claims-get')?.command).toContain('$CHILD_BENEFIT_FEDERATOR_TOKEN');
  });

  it('republishes only allowlisted lab tokens into story request sources', () => {
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-child"}');
    const result = publishRequestTokens(
      {
        request_source: {
          method: 'POST',
          url: 'http://localhost:4321/v1/evaluations',
          headers: {
            'x-api-key': '[runtime token hidden]',
            'Data-Purpose': 'https://id.registrystack.org/solmara/purpose/child-benefit-review'
          }
        },
        credential_source: {
          method: 'POST',
          url: 'http://pension-notary:8080/v1/credentials',
          headers: { 'x-api-key': '[runtime token hidden]' }
        }
      },
      tokens
    );

    expect(result.request_source.headers['x-api-key']).toBe('tok-child');
    expect(result.credential_source.headers['x-api-key']).toBe('[runtime token hidden]');
  });

  it('can match an allowlisted token from purpose when the URL is generic', () => {
    const tokens = parsePublishedTokens('{"nagdi-notary":"tok-nagdi"}');
    const result = publishRequestTokens(
      {
        request_source: {
          method: 'POST',
          url: 'https://lab.example/evaluations',
          headers: {
            'x-api-key': '[runtime token hidden]',
            'Data-Purpose': 'https://id.registrystack.org/solmara/purpose/livestock-movement-control'
          }
        }
      },
      tokens
    );

    expect(result.request_source.headers['x-api-key']).toBe('tok-nagdi');
  });
});
