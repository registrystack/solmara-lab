import { describe, expect, it, vi } from 'vitest';
import { PURPOSES } from '$lib/forms/descriptors';
import { LiveEvidenceProvider } from './index';

const ctx = { subject: '2300018263', delegatedTarget: '2300010248' };

function envelope(results: Array<{ claim_id: string; satisfied: boolean; value?: unknown }>, extra: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      result: {
        response_source: {
          status: 200,
          body: {
            results: results.map((item) => ({ ...item, value: item.value ?? item.satisfied })),
            signed_evidence: [{ protected: 'e30', payload: 'e30', signature: 'c2ln' }]
          }
        },
        source_trace: [{ authority: 'Source authority', service_id: 'registry-evidence', status: 200 }],
        ...extra
      }
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } }
  );
}

describe('LiveEvidenceProvider', () => {
  it('routes reviewed fields through the scenario runner with an Evidence purpose code', async () => {
    const fetcher = vi.fn(async () => envelope([{ claim_id: 'farmer-registered', satisfied: true }])) as unknown as typeof fetch;
    const provider = new LiveEvidenceProvider({ SCENARIO_RUNNER_URL: 'http://scenario-runner:8080' }, fetcher);
    const evaluation = await provider.evaluateDetailed(
      { id: 'registered-farmer', label: 'Registered farmer?', kind: 'verify' },
      ctx
    );

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, init] = vi.mocked(fetcher).mock.calls[0];
    expect(String(url)).toContain('/v1/scenarios/farmer-climate-smart-voucher/steps/positive/run');
    expect(JSON.parse(String(init?.body))).toEqual({ config: { purpose_override: PURPOSES.voucherEligibilityReview } });
    expect(evaluation.result.state).toBe('verified');
    expect(evaluation.proof.crypto.algorithm).toBe('Flattened JWS, EdDSA');
    expect(JSON.stringify(evaluation)).not.toContain('x-api-key');
  });

  it('blocks a dependent read until the relationship is proven', async () => {
    const fetcher = vi.fn() as unknown as typeof fetch;
    const provider = new LiveEvidenceProvider({ SCENARIO_RUNNER_URL: 'http://scenario-runner:8080' }, fetcher);
    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      ctx
    );

    expect(fetcher).not.toHaveBeenCalled();
    expect(evaluation.proof.status).toBe('denied');
    expect(evaluation.raw.request.url).toBe('solmara://citizen-portal/blocked-before-evidence');
  });

  it('selects one concept from a signed child-benefit assertion set', async () => {
    const fetcher = vi.fn(async () => envelope([
      { claim_id: 'birth-is-registered', satisfied: true },
      { claim_id: 'child-age-under-5', satisfied: true },
      { claim_id: 'population-record-active', satisfied: true },
      { claim_id: 'household-below-poverty-threshold', satisfied: true },
      { claim_id: 'not-already-enrolled', satisfied: true }
    ])) as unknown as typeof fetch;
    const provider = new LiveEvidenceProvider({ SCENARIO_RUNNER_URL: 'http://scenario-runner:8080' }, fetcher);
    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      ctx,
      { guardianLinkVerified: true }
    );

    expect(evaluation.result.state).toBe('verified');
    expect(evaluation.proof.answered).toContain('child-age-under-5 = true');
  });

  it('combines separate pension and survivor Evidence steps in the portal application', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/stop-payment/')) {
        return envelope([
          { claim_id: 'person-is-deceased', satisfied: true },
          { claim_id: 'pension-payment-active', satisfied: true }
        ]);
      }
      return envelope([{ claim_id: 'survivor-is-eligible', satisfied: true }]);
    }) as unknown as typeof fetch;
    const provider = new LiveEvidenceProvider({ SCENARIO_RUNNER_URL: 'http://scenario-runner:8080' }, fetcher);
    const evaluation = await provider.evaluateDetailed(
      { id: 'combined-support-eligibility', label: 'Eligibility', kind: 'decision' },
      ctx
    );

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(evaluation.result.authority).toBeUndefined();
    expect(evaluation.result.state).toBe('verified');
    expect(evaluation.raw.request.method).toBe('MULTI');
  });

  it('requires only the scenario runner URL when a live call is made', async () => {
    const provider = new LiveEvidenceProvider({}, vi.fn() as unknown as typeof fetch);
    await expect(
      provider.evaluateDetailed({ id: 'registered-farmer', label: 'Registered farmer?', kind: 'verify' }, ctx)
    ).rejects.toThrow('SCENARIO_RUNNER_URL is required');
  });
});
