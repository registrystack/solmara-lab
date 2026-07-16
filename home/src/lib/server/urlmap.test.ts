import { describe, expect, it } from 'vitest';
import { buildPublicUrlMap, mapPublicUrl, rewriteRequestUrls } from './urlmap';

describe('public URL map', () => {
  it('rewrites compose-internal notary hostnames to host-reachable localhost ports', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://child-benefit-federator:8080/v1/evaluations', map)).toBe(
      'http://localhost:4321/v1/evaluations'
    );
    expect(
      [
        'cra-notary:8081',
        'nia-notary:8081',
        'sro-notary:8081',
        'programme-notary:8081',
        'sipf-notary:8081',
        'nagdi-notary:8081'
      ].map((host) => mapPublicUrl(`http://${host}/v1/claims`, map))
    ).toEqual([
      'http://localhost:4325/v1/claims',
      'http://localhost:4326/v1/claims',
      'http://localhost:4327/v1/claims',
      'http://localhost:4328/v1/claims',
      'http://localhost:4322/v1/claims',
      'http://localhost:4323/v1/claims'
    ]);
  });

  it('rewrites relay and metadata hostnames from the same table', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://cra-civil-relay:8080/', map)).toBe('http://localhost:4311/');
    expect(mapPublicUrl('http://static-metadata:8080/metadata/catalog.json', map)).toBe(
      'http://localhost:4331/metadata/catalog.json'
    );
  });

  it('preserves path and query while swapping the origin', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://cra-notary:8081/v1/evaluations?trace=1', map)).toBe(
      'http://localhost:4325/v1/evaluations?trace=1'
    );
  });

  it('leaves already host-reachable URLs untouched', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://localhost:4321/v1/claims', map)).toBe('http://localhost:4321/v1/claims');
    expect(mapPublicUrl('https://child-benefit-federator.solmara.registrystack.org/v1/claims', map)).toBe(
      'https://child-benefit-federator.solmara.registrystack.org/v1/claims'
    );
  });

  it('returns non-URL strings unchanged', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('not a url', map)).toBe('not a url');
    expect(mapPublicUrl('', map)).toBe('');
  });

  it('merges an env-provided JSON override over the defaults', () => {
    const map = buildPublicUrlMap(
      JSON.stringify({
        'child-benefit-federator:8080': 'https://child-benefit-federator.solmara.registrystack.org'
      })
    );
    expect(mapPublicUrl('http://child-benefit-federator:8080/v1/claims', map)).toBe(
      'https://child-benefit-federator.solmara.registrystack.org/v1/claims'
    );
    // untouched defaults still apply
    expect(mapPublicUrl('http://sipf-notary:8081/v1/claims', map)).toBe(
      'http://localhost:4322/v1/claims'
    );
  });

  it('rewrites request_source and credential_source urls inside a run result', () => {
    const map = buildPublicUrlMap();
    const result = {
      request_source: { method: 'POST', url: 'http://child-benefit-federator:8080/v1/evaluations', headers: {} },
      credential_source: { method: 'POST', url: 'http://sipf-notary:8081/v1/credentials', headers: {} },
      request_sources: [{ method: 'POST', url: 'http://nia-notary:8081/v1/evaluations', headers: {} }],
      source_trace: [
        {
          request_source: {
            method: 'POST',
            url: 'http://cra-notary:8081/v1/evaluations',
            headers: {}
          }
        },
        {
          request_summary: {
            method: 'POST',
            url: 'http://sro-notary:8081/v1/evaluations'
          }
        }
      ],
      response_source: { status: 200 }
    };
    const mapped = rewriteRequestUrls(result, map);
    expect(mapped.request_source.url).toBe('http://localhost:4321/v1/evaluations');
    expect(mapped.credential_source.url).toBe('http://localhost:4322/v1/credentials');
    expect(mapped.request_sources[0].url).toBe('http://localhost:4326/v1/evaluations');
    expect(mapped.source_trace[0].request_source?.url).toBe('http://localhost:4325/v1/evaluations');
    expect(mapped.source_trace[1].request_summary?.url).toBe('http://localhost:4327/v1/evaluations');
    // does not mutate the original
    expect(result.request_source.url).toBe('http://child-benefit-federator:8080/v1/evaluations');
  });
});
