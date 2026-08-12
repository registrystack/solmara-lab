import { describe, expect, it } from 'vitest';
import type { RequestSource } from '$lib/types';
import { runnableRequestSources, toCurl } from './curl';

describe('runnableRequestSources', () => {
  const multiPreview: RequestSource = {
    method: 'MULTI',
    url: 'solmara://registry-evidence',
    purpose: 'citizen-self-service'
  };

  it('selects each executable Evidence call instead of the synthetic MULTI preview', () => {
    const sources: RequestSource[] = [
      {
        method: 'POST',
        url: 'https://localhost:4341/v1/evidence',
        headers: { Authorization: 'Bearer [runtime token hidden]' },
        body: { requirement: 'cra-citizen-record', purpose: 'citizen-self-service' }
      },
      {
        method: 'POST',
        url: 'https://localhost:4341/v1/evidence',
        headers: { Authorization: 'Bearer [runtime token hidden]' },
        body: { requirement: 'nia-citizen-status', purpose: 'citizen-self-service' }
      }
    ];

    const commands = runnableRequestSources(multiPreview, sources).map((source) => toCurl(source));

    expect(commands).toHaveLength(2);
    expect(commands[0]).toContain("curl -sS -X POST 'https://localhost:4341/v1/evidence'");
    expect(commands[1]).toContain("curl -sS -X POST 'https://localhost:4341/v1/evidence'");
    expect(commands.join('\n')).not.toContain('solmara://registry-evidence');
  });

  it('uses the primary request when no underlying calls are present', () => {
    const request: RequestSource = {
      method: 'GET',
      url: 'http://localhost:4321/v1/claims',
      headers: {}
    };

    expect(runnableRequestSources(request, undefined)).toEqual([request]);
    expect(runnableRequestSources(request, [])).toEqual([request]);
  });
});
