import { describe, expect, it } from 'vitest';
import { buildPublicUrlMap, mapPublicUrl, rewriteRequestUrls } from './urlmap';

describe('public URL map', () => {
  it('keeps each public authority Evidence origin distinct', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('https://cra-evidence.solmara.registrystack.org/v1/evidence', map)).toContain('cra-evidence');
    expect(mapPublicUrl('https://nia-evidence.solmara.registrystack.org/v1/evidence', map)).toContain('nia-evidence');
  });

  it('rewrites the five Relay V2 and programme hostnames', () => {
    const map = buildPublicUrlMap();
    expect(mapPublicUrl('http://cra-relay:8080/ready', map)).toBe('http://localhost:4311/ready');
    expect(mapPublicUrl('http://sipf-relay:8080/ready', map)).toBe('http://localhost:4315/ready');
    expect(mapPublicUrl('http://child-benefit-federator:8080/v1/evaluations', map)).toBe('http://localhost:4321/v1/evaluations');
  });

  it('merges an environment override and preserves path and query', () => {
    const map = buildPublicUrlMap(JSON.stringify({ 'cra-evidence.solmara.registrystack.org': 'https://cra.example' }));
    expect(mapPublicUrl('https://cra-evidence.solmara.registrystack.org/v1/evidence?trace=1', map)).toBe('https://cra.example/v1/evidence?trace=1');
  });

  it('rewrites nested sources without mutating the input', () => {
    const map = buildPublicUrlMap();
    const result = {
      request_source: { method: 'POST', url: 'http://cra-relay:8080/v2/resources/civil/lookup' },
      request_sources: [{ method: 'POST', url: 'http://nia-relay:8080/v2/resources/population/lookup' }],
      source_trace: [{ request_source: { method: 'POST', url: 'http://sipf-relay:8080/v2/resources/pension/lookup' } }]
    };
    const mapped = rewriteRequestUrls(result, map);
    expect(mapped.request_source.url).toContain('localhost:4311');
    expect(mapped.request_sources[0].url).toContain('localhost:4312');
    expect(mapped.source_trace[0].request_source?.url).toContain('localhost:4315');
    expect(result.request_source.url).toContain('cra-relay:8080');
  });
});
