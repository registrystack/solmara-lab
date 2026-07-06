import { describe, expect, it } from 'vitest';
import { buildPublicUrlMap, mapPublicUrl, rewriteRequestUrls } from './urlmap';

describe('public URL map', () => {
  it('rewrites compose-internal notary hostnames to host-reachable localhost ports', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://child-benefit-notary:8080/v1/evaluations', map)).toBe(
      'http://localhost:4321/v1/evaluations'
    );
    expect(mapPublicUrl('http://pension-notary:8080/v1/claims', map)).toBe(
      'http://localhost:4322/v1/claims'
    );
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
    expect(mapPublicUrl('http://citizen-notary:8080/v1/evaluations?trace=1', map)).toBe(
      'http://localhost:4324/v1/evaluations?trace=1'
    );
  });

  it('leaves already host-reachable URLs untouched', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://localhost:4321/v1/claims', map)).toBe('http://localhost:4321/v1/claims');
    expect(mapPublicUrl('https://child-benefit-notary.lab.registrystack.org/v1/claims', map)).toBe(
      'https://child-benefit-notary.lab.registrystack.org/v1/claims'
    );
  });

  it('returns non-URL strings unchanged', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('not a url', map)).toBe('not a url');
    expect(mapPublicUrl('', map)).toBe('');
  });

  it('merges an env-provided JSON override over the defaults', () => {
    const map = buildPublicUrlMap(
      JSON.stringify({ 'child-benefit-notary:8080': 'https://child-benefit-notary.lab.registrystack.org' })
    );
    expect(mapPublicUrl('http://child-benefit-notary:8080/v1/claims', map)).toBe(
      'https://child-benefit-notary.lab.registrystack.org/v1/claims'
    );
    // untouched defaults still apply
    expect(mapPublicUrl('http://pension-notary:8080/v1/claims', map)).toBe(
      'http://localhost:4322/v1/claims'
    );
  });

  it('rewrites request_source and credential_source urls inside a run result', () => {
    const map = buildPublicUrlMap();
    const result = {
      request_source: { method: 'POST', url: 'http://child-benefit-notary:8080/v1/evaluations', headers: {} },
      credential_source: { method: 'POST', url: 'http://child-benefit-notary:8080/v1/credentials', headers: {} },
      response_source: { status: 200 }
    };
    const mapped = rewriteRequestUrls(result, map);
    expect(mapped.request_source.url).toBe('http://localhost:4321/v1/evaluations');
    expect(mapped.credential_source.url).toBe('http://localhost:4321/v1/credentials');
    // does not mutate the original
    expect(result.request_source.url).toBe('http://child-benefit-notary:8080/v1/evaluations');
  });
});
