import { describe, expect, it } from 'vitest';
import type { RequestSource } from '$lib/types';
import { runnableRequestSources, toCurl } from './curl';

describe('runnableRequestSources', () => {
  const multiPreview: RequestSource = {
    method: 'MULTI',
    url: 'solmara://authority-notaries',
    headers: { 'Data-Purpose': 'citizen-self-service' }
  };

  it('selects each executable authority call instead of the synthetic MULTI preview', () => {
    const sources: RequestSource[] = [
      {
        method: 'POST',
        url: 'http://localhost:4325/v1/evaluations',
        headers: { 'x-api-key': 'tok-cra-citizen' },
        body: { claims: ['civil-record-linked'] }
      },
      {
        method: 'POST',
        url: 'http://localhost:4326/v1/evaluations',
        headers: { 'x-api-key': 'tok-nia-citizen' },
        body: { claims: ['citizen-population-record-active'] }
      }
    ];

    const commands = runnableRequestSources(multiPreview, sources).map((source) => toCurl(source));

    expect(commands).toHaveLength(2);
    expect(commands[0]).toContain("curl -sS -X POST 'http://localhost:4325/v1/evaluations'");
    expect(commands[1]).toContain("curl -sS -X POST 'http://localhost:4326/v1/evaluations'");
    expect(commands.join('\n')).not.toContain('solmara://authority-notaries');
  });

  it('uses the primary request when no underlying calls are present', () => {
    const request: RequestSource = {
      method: 'GET',
      url: 'http://localhost:4325/v1/claims',
      headers: {}
    };

    expect(runnableRequestSources(request, undefined)).toEqual([request]);
    expect(runnableRequestSources(request, [])).toEqual([request]);
  });
});
