import { describe, expect, it } from 'vitest';
import { buildPublicUrlMap, mapPublicUrl, rewriteRequestUrls } from './urlmap';

describe('public URL map', () => {
  it('rewrites internal Evidence and Mint origins to the local TLS gateway', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('https://evidence.solmara.invalid/v1/evidence', map)).toBe(
      'https://localhost:4341/v1/evidence'
    );
    expect(mapPublicUrl('https://mint.evidence.solmara.invalid/token', map)).toBe(
      'https://localhost:4341/token'
    );
  });

  it('rewrites Relay and application hostnames from the same table', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://cra-civil-relay:8080/', map)).toBe('http://localhost:4311/');
    expect(mapPublicUrl('http://child-benefit-federator:8080/v1/evaluations', map)).toBe(
      'http://localhost:4321/v1/evaluations'
    );
  });

  it('preserves path and query while swapping an Evidence origin', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('https://evidence.solmara.invalid/v1/evidence?trace=1', map)).toBe(
      'https://localhost:4341/v1/evidence?trace=1'
    );
  });

  it('leaves already host-reachable and non-URL values untouched', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://localhost:4321/v1/claims', map)).toBe('http://localhost:4321/v1/claims');
    expect(mapPublicUrl('not a url', map)).toBe('not a url');
  });

  it('merges an environment override over the defaults', () => {
    const map = buildPublicUrlMap(JSON.stringify({ 'evidence.solmara.invalid': 'https://evidence.example' }));
    expect(mapPublicUrl('https://evidence.solmara.invalid/v1/evidence', map)).toBe('https://evidence.example/v1/evidence');
    expect(mapPublicUrl('http://sipf-pensions-relay:8080/ready', map)).toBe('http://localhost:4315/ready');
  });

  it('rewrites nested request sources without mutating the input', () => {
    const map = buildPublicUrlMap();
    const result = {
      request_source: { method: 'POST', url: 'https://evidence.solmara.invalid/v1/evidence', headers: {} },
      request_sources: [{ method: 'POST', url: 'https://evidence.solmara.invalid/v1/evidence', headers: {} }],
      source_trace: [{ request_source: { method: 'GET', url: 'http://cra-civil-relay:8080/records/civil_people' } }]
    };
    const mapped = rewriteRequestUrls(result, map);
    expect(mapped.request_source.url).toBe('https://localhost:4341/v1/evidence');
    expect(mapped.request_sources[0].url).toBe('https://localhost:4341/v1/evidence');
    expect(mapped.source_trace[0].request_source?.url).toBe('http://localhost:4311/records/civil_people');
    expect(result.request_source.url).toBe('https://evidence.solmara.invalid/v1/evidence');
  });
});
