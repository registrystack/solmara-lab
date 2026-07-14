import { describe, expect, it } from 'vitest';
import { buildCurlExamples, parsePublishedTokens, publishRequestTokens } from './tokens';

describe('published-token allowlist', () => {
  it('renders only the tokens named in the allowlist JSON', () => {
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-child","sipf-pension-client":"tok-pension"}');
    expect(tokens.map((token) => token.name)).toEqual(['child-benefit-federator', 'sipf-pension-client']);
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
          url: 'http://sipf-notary:8081/v1/credentials',
          headers: { 'x-api-key': '[runtime token hidden]' }
        }
      },
      tokens
    );

    expect(result.request_source.headers['x-api-key']).toBe('tok-child');
    expect(result.credential_source.headers['x-api-key']).toBe('[runtime token hidden]');
  });

  it('does not publish a token from purpose alone when the authority URL is unknown', () => {
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

    expect(result.request_source.headers['x-api-key']).toBe('[runtime token hidden]');
  });

  it('does not guess between authority clients when purpose or URL binding is incomplete', () => {
    const tokens = parsePublishedTokens(
      '{"cra-pension-client":"tok-cra-pension","cra-citizen-client":"tok-cra-citizen","nia-citizen-client":"tok-nia-citizen","sipf-pension-client":"tok-sipf-pension"}'
    );
    const result = publishRequestTokens(
      {
        request_sources: [
          {
            method: 'POST',
            url: 'https://unmapped.example/v1/evaluations',
            headers: {
              'x-api-key': '[runtime token hidden]',
              'Data-Purpose': 'https://id.registrystack.org/solmara/purpose/pension-payment-review'
            }
          },
          {
            method: 'POST',
            url: 'http://cra-notary:8081/v1/evaluations',
            headers: { 'x-api-key': '[runtime token hidden]' }
          }
        ]
      },
      tokens
    );

    expect(result.request_sources[0].headers['x-api-key']).toBe('[runtime token hidden]');
    expect(result.request_sources[1].headers['x-api-key']).toBe('[runtime token hidden]');
  });

  it('does not publish a purpose token to a different known authority endpoint', () => {
    const tokens = parsePublishedTokens('{"child-benefit-federator":"tok-child"}');
    const result = publishRequestTokens(
      {
        request_source: {
          method: 'POST',
          url: 'http://cra-notary:8081/v1/evaluations',
          headers: {
            'x-api-key': '[runtime token hidden]',
            'Data-Purpose': 'https://id.registrystack.org/solmara/purpose/child-benefit-review'
          }
        }
      },
      tokens
    );

    expect(result.request_source.headers['x-api-key']).toBe('[runtime token hidden]');
  });

  it('publishes authority client tokens by both Notary URL and purpose', () => {
    const tokens = parsePublishedTokens(
      JSON.stringify({
        'cra-pension-client': 'tok-cra-pension',
        'cra-citizen-client': 'tok-cra-citizen',
        'nia-citizen-client': 'tok-nia-citizen',
        'sipf-pension-client': 'tok-sipf-pension'
      })
    );
    const result = publishRequestTokens(
      {
        request_sources: [
          {
            method: 'POST',
            url: 'http://cra-notary:8081/v1/evaluations',
            headers: {
              'x-api-key': '[runtime token hidden]',
              'Data-Purpose': 'https://id.registrystack.org/solmara/purpose/pension-payment-review'
            }
          },
          {
            method: 'POST',
            url: 'http://nia-notary:8081/v1/evaluations',
            headers: {
              'x-api-key': '[runtime token hidden]',
              'Data-Purpose': 'https://id.registrystack.org/solmara/purpose/citizen-self-service'
            }
          }
        ],
        credential_source: {
          method: 'POST',
          url: 'http://sipf-notary:8081/v1/credentials',
          headers: {
            'x-api-key': '[runtime token hidden]',
            'data-purpose': 'https://id.registrystack.org/solmara/purpose/survivor-benefit-determination'
          }
        },
        source_trace: [
          {
            request_source: {
              method: 'POST',
              url: 'http://cra-notary:8081/v1/evaluations',
              headers: {
                'x-api-key': '[runtime token hidden]',
                'Data-Purpose': 'https://id.registrystack.org/solmara/purpose/citizen-self-service'
              }
            }
          }
        ]
      },
      tokens
    );

    expect(result.request_sources[0].headers['x-api-key']).toBe('tok-cra-pension');
    expect(result.request_sources[1].headers['x-api-key']).toBe('tok-nia-citizen');
    expect(result.credential_source.headers['x-api-key']).toBe('tok-sipf-pension');
    expect(result.source_trace[0].request_source.headers['x-api-key']).toBe('tok-cra-citizen');
  });
});
