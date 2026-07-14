import { describe, expect, it, vi } from 'vitest';
import { LiveEvidenceProvider } from '.';
import { PURPOSES } from '$lib/forms/descriptors';
import { CLAIM_RESULT_FORMAT } from '$lib/providers/mock/wire';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

function serviceIdFor(claimId: string): string {
  if (claimId === 'citizen-population-record-active') return 'nia-notary';
  if (claimId === 'pension-payment-active' || claimId === 'survivor-is-eligible') {
    return 'sipf-notary';
  }
  if (claimId.startsWith('farmer-')) return 'nagdi-notary';
  return 'cra-notary';
}

function evaluationResult(claimId: string, satisfied: boolean): Record<string, unknown> {
  const evaluationId = `eval-${claimId}`;
  const claimVersion = '1';
  return {
    claim_id: claimId,
    claim_version: claimVersion,
    subject_type: 'person',
    target_ref: { handle: 'rnref:v1:test-target' },
    value: satisfied,
    satisfied,
    disclosure: 'predicate',
    evaluation_id: evaluationId,
    format: CLAIM_RESULT_FORMAT,
    issued_at: '2026-07-15T00:00:00Z',
    expires_at: null,
    provenance: {
      schema_version: 'registry-notary-claim-provenance/v2',
      generated_by: {
        type: 'claim_evaluation',
        service_id: serviceIdFor(claimId),
        evaluation_id: evaluationId,
        claim_id: claimId,
        claim_version: claimVersion
      },
      used: { relay_consultation_count: 1 },
      derived_from: []
    }
  };
}

function evaluationResponse(claimId: string, satisfied: boolean): Response {
  return jsonResponse({
    results: [evaluationResult(claimId, satisfied)]
  });
}

function fetchInit(fetcher: ReturnType<typeof vi.fn>, callIndex: number): RequestInit {
  const init: unknown = fetcher.mock.calls[callIndex]?.[1];
  if (typeof init !== 'object' || init === null) throw new Error('missing fetch init');
  // Vitest stores the RequestInit object as the second recorded fetch argument.
  return init as RequestInit;
}

describe('LiveEvidenceProvider', () => {
  it('calls the CRA Notary directly with its pension-purpose token and server-selected subject', async () => {
    const fetcher = vi.fn().mockResolvedValue(evaluationResponse('person-is-deceased', true));
    const provider = new LiveEvidenceProvider(
      {
        CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
        CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
      { subject: '2300018263', selectedSubject: '2300109568' }
    );

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe(
      'https://cra-notary.solmara.registrystack.org/v1/evaluations'
    );
    const init = fetchInit(fetcher, 0);
    expect(init.headers).toEqual({
      'x-api-key': 'cra-pension-token',
      Accept: CLAIM_RESULT_FORMAT,
      'Data-Purpose': PURPOSES.pensionPaymentReview,
      'Content-Type': 'application/json'
    });
    expect(JSON.parse(String(init.body))).toEqual({
      claims: ['person-is-deceased'],
      purpose: PURPOSES.pensionPaymentReview,
      disclosure: 'predicate',
      format: CLAIM_RESULT_FORMAT,
      relationship: { type: 'self' },
      target: {
        type: 'Person',
        identifiers: [{ scheme: 'solmara_uin', value: '2300109568' }]
      }
    });
    expect(evaluation.result.display).toBe('Death registered: yes');
    expect(JSON.stringify(fetcher.mock.calls)).not.toContain('relay');
  });

  it('fails closed when a successful authority response omits the predicate decision', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        results: [
          {
            claim_id: 'person-is-deceased',
            claim_version: '1',
            disclosure: 'predicate',
            evaluation_id: 'eval-malformed',
            issued_at: '2026-07-15T00:00:00Z'
          }
        ]
      })
    );
    const provider = new LiveEvidenceProvider(
      {
        CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
        CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
      { subject: '2300109568' }
    );

    expect(evaluation.result.state).toBe('error');
    expect(evaluation.proof.status).toBe('error');
    expect(evaluation.result.asOf).toBeUndefined();
  });

  for (const requiredField of [
    'claim_version',
    'evaluation_id',
    'issued_at',
    'format',
    'provenance'
  ]) {
    it(`rejects a direct Notary result missing ${requiredField} without filling it locally`, async () => {
      const result = evaluationResult('person-is-deceased', true);
      delete result[requiredField];
      const fetcher = vi.fn().mockResolvedValue(jsonResponse({ results: [result] }));
      const provider = new LiveEvidenceProvider(
        {
          CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
          CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token'
        },
        fetcher
      );

      const evaluation = await provider.evaluateDetailed(
        { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
        { subject: '2300109568' }
      );

      expect(evaluation.result.state).toBe('error');
      expect(evaluation.proof.status).toBe('error');
      expect(evaluation.raw.response.body).toEqual({ results: [] });
      expect(evaluation.result.asOf).toBeUndefined();
    });
  }

  it('rejects direct provenance that does not bind to the expected authority and result', async () => {
    const result = evaluationResult('person-is-deceased', true);
    // The fixture builder always installs this provenance object before the test mutates it.
    const provenance = result.provenance as {
      generated_by: { service_id: string; evaluation_id: string };
    };
    provenance.generated_by.service_id = 'nia-notary';
    provenance.generated_by.evaluation_id = 'eval-other';
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ results: [result] }));
    const provider = new LiveEvidenceProvider(
      {
        CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
        CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
      { subject: '2300109568' }
    );

    expect(evaluation.result.state).toBe('error');
    expect(evaluation.proof.status).toBe('error');
    expect(evaluation.raw.response.body).toEqual({ results: [] });
  });

  it('does not present an expired direct claim result as verified', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T12:00:00Z'));
    try {
      const result = evaluationResult('person-is-deceased', true);
      result.issued_at = '2026-07-10T00:00:00Z';
      result.expires_at = '2026-07-14T00:00:00Z';
      const provider = new LiveEvidenceProvider(
        {
          CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
          CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token'
        },
        vi.fn().mockResolvedValue(jsonResponse({ results: [result] }))
      );

      const evaluation = await provider.evaluateDetailed(
        { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
        { subject: '2300109568' }
      );

      expect(evaluation.result).toMatchObject({
        state: 'stale',
        display: 'person-is-deceased: expired evidence, refresh required',
        asOf: '2026-07-10T00:00:00Z'
      });
      expect(evaluation.proof.status).toBe('error');
    } finally {
      vi.useRealTimers();
    }
  });

  it('derives the pension-stop decision in the portal from independent CRA and SIPF claims', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(evaluationResponse('person-is-deceased', true))
      .mockResolvedValueOnce(evaluationResponse('pension-payment-active', true));
    const provider = new LiveEvidenceProvider(
      {
        CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
        CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token',
        SIPF_NOTARY_URL: 'https://sipf-notary.solmara.registrystack.org',
        SIPF_PENSION_CLIENT_TOKEN: 'sipf-pension-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'disability-determination', label: 'Stop pension?', kind: 'verify' },
      { subject: '2300109568' }
    );

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls.map((call) => call[0])).toEqual([
      'https://cra-notary.solmara.registrystack.org/v1/evaluations',
      'https://sipf-notary.solmara.registrystack.org/v1/evaluations'
    ]);
    const requests = fetcher.mock.calls.map((_call, index) =>
      JSON.parse(String(fetchInit(fetcher, index).body))
    );
    expect(requests.map((request) => request.claims)).toEqual([
      ['person-is-deceased'],
      ['pension-payment-active']
    ]);
    expect(JSON.stringify(requests)).not.toContain('pension-payment-should-stop');
    expect(evaluation.result.display).toBe('Pension payment should stop: yes');
    expect(evaluation.result.authority).toBeUndefined();
    expect(evaluation.proof.authority).toBeUndefined();
    expect(evaluation.raw.request.method).toBe('MULTI');
    expect(evaluation.raw.response.body).toMatchObject({
      orchestration: { service_id: 'citizen-portal', decision: 'application_composed' },
      derived_decisions: { 'pension-payment-should-stop': true },
      source_trace: [
        { service_id: 'cra-notary', claims: ['person-is-deceased'] },
        { service_id: 'sipf-notary', claims: ['pension-payment-active'] }
      ]
    });
  });

  it('uses the oldest source timestamp for a composed decision', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T12:00:00Z'));
    try {
      const civil = evaluationResult('person-is-deceased', true);
      civil.issued_at = '2026-07-14T00:00:00Z';
      civil.expires_at = '2026-08-14T00:00:00Z';
      const payment = evaluationResult('pension-payment-active', true);
      payment.issued_at = '2026-07-10T00:00:00Z';
      payment.expires_at = '2026-08-10T00:00:00Z';
      const fetcher = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ results: [civil] }))
        .mockResolvedValueOnce(jsonResponse({ results: [payment] }));
      const provider = new LiveEvidenceProvider(
        {
          CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
          CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token',
          SIPF_NOTARY_URL: 'https://sipf-notary.solmara.registrystack.org',
          SIPF_PENSION_CLIENT_TOKEN: 'sipf-pension-token'
        },
        fetcher
      );

      const evaluation = await provider.evaluateDetailed(
        { id: 'disability-determination', label: 'Stop pension?', kind: 'verify' },
        { subject: '2300109568' }
      );

      expect(evaluation.result.asOf).toBe('2026-07-10T00:00:00Z');
      expect(evaluation.result.state).toBe('verified');
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not compose a positive decision when any source result is expired', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T12:00:00Z'));
    try {
      const civil = evaluationResult('person-is-deceased', true);
      civil.issued_at = '2026-07-10T00:00:00Z';
      civil.expires_at = '2026-07-14T00:00:00Z';
      const payment = evaluationResult('pension-payment-active', true);
      payment.issued_at = '2026-07-14T00:00:00Z';
      payment.expires_at = '2026-08-14T00:00:00Z';
      const provider = new LiveEvidenceProvider(
        {
          CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
          CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token',
          SIPF_NOTARY_URL: 'https://sipf-notary.solmara.registrystack.org',
          SIPF_PENSION_CLIENT_TOKEN: 'sipf-pension-token'
        },
        vi
          .fn()
          .mockResolvedValueOnce(jsonResponse({ results: [civil] }))
          .mockResolvedValueOnce(jsonResponse({ results: [payment] }))
      );

      const evaluation = await provider.evaluateDetailed(
        { id: 'disability-determination', label: 'Stop pension?', kind: 'verify' },
        { subject: '2300109568' }
      );

      expect(evaluation.result.state).toBe('stale');
      expect(evaluation.proof.status).toBe('error');
      expect(evaluation.raw.response.body).toMatchObject({
        derived_decisions: { 'pension-payment-should-stop': null }
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows the direct SIPF payment predicate without inventing a household conflict result', async () => {
    const fetcher = vi.fn().mockResolvedValue(evaluationResponse('pension-payment-active', true));
    const provider = new LiveEvidenceProvider(
      {
        SIPF_NOTARY_URL: 'https://sipf-notary.solmara.registrystack.org',
        SIPF_PENSION_CLIENT_TOKEN: 'sipf-pension-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'pension-payment-active', label: 'Pension payment active?', kind: 'verify' },
      { subject: '2300109568' }
    );

    expect(evaluation.result.display).toBe('Pension payment active: yes');
    expect(JSON.stringify(evaluation)).not.toMatch(/conflict|household-size/);
  });

  it('derives only a boolean survivor decision and never invents a support band', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(evaluationResponse('person-is-deceased', true))
      .mockResolvedValueOnce(evaluationResponse('pension-payment-active', true))
      .mockResolvedValueOnce(evaluationResponse('survivor-is-eligible', true));
    const provider = new LiveEvidenceProvider(
      {
        CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
        CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token',
        SIPF_NOTARY_URL: 'https://sipf-notary.solmara.registrystack.org',
        SIPF_PENSION_CLIENT_TOKEN: 'sipf-pension-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'combined-support-eligibility', label: 'Eligibility decision', kind: 'decision' },
      { subject: '2300109568' }
    );

    expect(evaluation.result.display).toBe('Survivor benefit eligible: yes');
    expect(evaluation.raw.response.body).toMatchObject({
      derived_decisions: { 'survivor-benefit-eligible': true }
    });
    expect(JSON.stringify(evaluation)).not.toMatch(/support.band|band B/i);
  });

  it('routes survivor evidence to SIPF under the survivor-benefit purpose', async () => {
    const fetcher = vi.fn().mockResolvedValue(evaluationResponse('survivor-is-eligible', true));
    const provider = new LiveEvidenceProvider(
      {
        SIPF_NOTARY_URL: 'https://sipf-notary.solmara.registrystack.org',
        SIPF_PENSION_CLIENT_TOKEN: 'sipf-pension-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'functioning-assessment', label: 'Survivor eligible?', kind: 'verify' },
      { subject: '2300118698' }
    );

    expect(fetcher.mock.calls[0][0]).toBe(
      'https://sipf-notary.solmara.registrystack.org/v1/evaluations'
    );
    expect(fetchInit(fetcher, 0).headers).toMatchObject({
      'x-api-key': 'sipf-pension-token',
      'Data-Purpose': PURPOSES.survivorBenefitDetermination
    });
    expect(evaluation.proof.crypto).toMatchObject({
      issuerKey: 'Not applicable for claim-result evaluation',
      credential: 'Claim results only; no credential issued by the portal'
    });
  });

  it('keeps CRA and NIA citizen evidence separate and names NIA as credential owner', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(evaluationResponse('civil-record-linked', true))
      .mockResolvedValueOnce(evaluationResponse('citizen-population-record-active', true));
    const provider = new LiveEvidenceProvider(
      {
        CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
        CRA_CITIZEN_CLIENT_TOKEN: 'cra-citizen-token',
        NIA_NOTARY_URL: 'https://nia-notary.solmara.registrystack.org',
        NIA_CITIZEN_CLIENT_TOKEN: 'nia-citizen-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'citizen-record-status', label: 'Citizen record status', kind: 'verify' },
      { subject: '2300018263' }
    );

    expect(fetcher.mock.calls.map((call) => call[0])).toEqual([
      'https://cra-notary.solmara.registrystack.org/v1/evaluations',
      'https://nia-notary.solmara.registrystack.org/v1/evaluations'
    ]);
    expect(fetcher.mock.calls.map((_call, index) => fetchInit(fetcher, index).headers)).toEqual([
      {
        'x-api-key': 'cra-citizen-token',
        Accept: CLAIM_RESULT_FORMAT,
        'Data-Purpose': PURPOSES.citizenSelfService,
        'Content-Type': 'application/json'
      },
      {
        'x-api-key': 'nia-citizen-token',
        Accept: CLAIM_RESULT_FORMAT,
        'Data-Purpose': PURPOSES.citizenSelfService,
        'Content-Type': 'application/json'
      }
    ]);
    expect(evaluation.result.display).toBe('Civil and population records active: yes');
    expect(evaluation.proof.crypto).toMatchObject({
      issuerKey: 'Not applicable for claim-result evaluation',
      credential: 'Application decision only; no credential issued by the portal'
    });
    expect(JSON.stringify(evaluation)).not.toMatch(/CSR-BIRTH|certificate_id|issued_on/);
  });

  it('denies delegated reads before configuration lookup or any upstream call', async () => {
    const fetcher = vi.fn();
    const provider = new LiveEvidenceProvider({}, fetcher);

    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      { subject: '2300018263', delegatedTarget: '2300010248' }
    );

    expect(fetcher).not.toHaveBeenCalled();
    expect(evaluation.raw.request.url).toBe(
      'solmara://citizen-portal/blocked-before-authority-call'
    );
    expect(evaluation.raw.response.status).toBe(403);
    expect(evaluation.result.reasonCode).toBe('relationship_not_proven');
  });

  it('uses the child application ordinary JSON evidence contract after the guardian gate', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'solmara-child-benefit-evidence/v1',
        evidence_set_id: 'cbe_live_1',
        orchestration: {
          service_id: 'child-benefit-federator',
          decision: 'not_composed'
        },
        purpose: PURPOSES.childBenefitReview,
        target: { type: 'Person', identifier_schemes: ['solmara_uin'] },
        results: [
          {
            claim_id: 'child-age-under-5',
            claim_version: '1',
            disclosure: 'predicate',
            format: CLAIM_RESULT_FORMAT,
            issued_at: '2026-07-15T00:00:00Z',
            expires_at: '2026-08-14T00:00:00Z',
            satisfied: true,
            authority: 'Civil Registration Authority',
            notary_service_id: 'cra-notary'
          }
        ],
        source_trace: [
          {
            authority: 'Civil Registration Authority',
            service_id: 'cra-notary',
            claims: ['child-age-under-5']
          }
        ]
      })
    );
    const provider = new LiveEvidenceProvider(
      {
        CHILD_BENEFIT_FEDERATOR_URL:
          'https://child-benefit-federator.solmara.registrystack.org',
        CHILD_BENEFIT_FEDERATOR_TOKEN: 'child-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      { subject: '2300018263', delegatedTarget: '2300010248' },
      { guardianLinkVerified: true }
    );

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe(
      'https://child-benefit-federator.solmara.registrystack.org/v1/evaluations'
    );
    const init = fetchInit(fetcher, 0);
    expect(init.headers).toEqual({
      'x-api-key': 'child-token',
      Accept: 'application/json',
      'Data-Purpose': PURPOSES.childBenefitReview,
      'Content-Type': 'application/json'
    });
    expect(JSON.parse(String(init.body))).toEqual({
      target: {
        type: 'Person',
        identifiers: [{ scheme: 'solmara_uin', value: '2300010248' }]
      },
      claims: ['child-age-under-5'],
      disclosure: 'predicate',
      format: 'application/json'
    });
    expect(evaluation.raw.response.body).toMatchObject({
      schema_version: 'solmara-child-benefit-evidence/v1',
      evidence_set_id: 'cbe_live_1',
      orchestration: { decision: 'not_composed' },
      source_trace: [{ service_id: 'cra-notary' }]
    });
    expect(evaluation.proof.crypto).toMatchObject({
      algorithm: 'Ordinary JSON response; no application signature asserted',
      credential: 'Minimized source-attributed predicate result',
      auditId: 'evidence-set:cbe_live_1'
    });
    expect(JSON.stringify(evaluation.proof.crypto)).not.toMatch(/federated|federation/);
    expect(JSON.stringify(evaluation.proof.crypto)).not.toContain('SD-JWT');
  });

  it('rejects a child predicate that lacks matching source attribution', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'solmara-child-benefit-evidence/v1',
        evidence_set_id: 'cbe_unattributed',
        orchestration: {
          service_id: 'child-benefit-federator',
          decision: 'not_composed'
        },
        purpose: PURPOSES.childBenefitReview,
        target: { type: 'Person', identifier_schemes: ['solmara_uin'] },
        results: [
          {
            claim_id: 'child-age-under-5',
            claim_version: '1',
            disclosure: 'predicate',
            format: CLAIM_RESULT_FORMAT,
            issued_at: '2026-07-15T00:00:00Z',
            expires_at: null,
            satisfied: true,
            authority: 'Civil Registration Authority',
            notary_service_id: 'cra-notary'
          }
        ],
        source_trace: []
      })
    );
    const provider = new LiveEvidenceProvider(
      {
        CHILD_BENEFIT_FEDERATOR_URL:
          'https://child-benefit-federator.solmara.registrystack.org',
        CHILD_BENEFIT_FEDERATOR_TOKEN: 'child-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      { subject: '2300018263', delegatedTarget: '2300010248' },
      { guardianLinkVerified: true }
    );

    expect(evaluation.result.state).toBe('error');
    expect(evaluation.proof.status).toBe('error');
    expect(evaluation.result.display).toBe('child-age-under-5: not returned');
    expect(evaluation.result.asOf).toBeUndefined();
  });

  it('does not present expired child application evidence as verified', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T12:00:00Z'));
    try {
      const fetcher = vi.fn().mockResolvedValue(
        jsonResponse({
          schema_version: 'solmara-child-benefit-evidence/v1',
          evidence_set_id: 'cbe_expired',
          orchestration: {
            service_id: 'child-benefit-federator',
            decision: 'not_composed'
          },
          purpose: PURPOSES.childBenefitReview,
          target: { type: 'Person', identifier_schemes: ['solmara_uin'] },
          results: [
            {
              claim_id: 'child-age-under-5',
              claim_version: '1',
              disclosure: 'predicate',
              format: CLAIM_RESULT_FORMAT,
              issued_at: '2026-07-10T00:00:00Z',
              expires_at: '2026-07-14T00:00:00Z',
              satisfied: true,
              authority: 'Civil Registration Authority',
              notary_service_id: 'cra-notary'
            }
          ],
          source_trace: [
            {
              authority: 'Civil Registration Authority',
              service_id: 'cra-notary',
              claims: ['child-age-under-5']
            }
          ]
        })
      );
      const provider = new LiveEvidenceProvider(
        {
          CHILD_BENEFIT_FEDERATOR_URL:
            'https://child-benefit-federator.solmara.registrystack.org',
          CHILD_BENEFIT_FEDERATOR_TOKEN: 'child-token'
        },
        fetcher
      );

      const evaluation = await provider.evaluateDetailed(
        { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
        { subject: '2300018263', delegatedTarget: '2300010248' },
        { guardianLinkVerified: true }
      );

      expect(evaluation.result.state).toBe('stale');
      expect(evaluation.result.display).toBe('child-age-under-5: expired evidence, refresh required');
      expect(evaluation.proof.status).toBe('error');
    } finally {
      vi.useRealTimers();
    }
  });

  it('rejects internally consistent child attribution from the wrong authority', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      jsonResponse({
        schema_version: 'solmara-child-benefit-evidence/v1',
        evidence_set_id: 'cbe_wrong_authority',
        orchestration: {
          service_id: 'child-benefit-federator',
          decision: 'not_composed'
        },
        purpose: PURPOSES.childBenefitReview,
        target: { type: 'Person', identifier_schemes: ['solmara_uin'] },
        results: [
          {
            claim_id: 'child-age-under-5',
            claim_version: '1',
            disclosure: 'predicate',
            format: CLAIM_RESULT_FORMAT,
            issued_at: '2026-07-15T00:00:00Z',
            expires_at: null,
            satisfied: true,
            authority: 'National Identity Agency',
            notary_service_id: 'nia-notary'
          }
        ],
        source_trace: [
          {
            authority: 'National Identity Agency',
            service_id: 'nia-notary',
            claims: ['child-age-under-5']
          }
        ]
      })
    );
    const provider = new LiveEvidenceProvider(
      {
        CHILD_BENEFIT_FEDERATOR_URL:
          'https://child-benefit-federator.solmara.registrystack.org',
        CHILD_BENEFIT_FEDERATOR_TOKEN: 'child-token'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      { subject: '2300018263', delegatedTarget: '2300010248' },
      { guardianLinkVerified: true }
    );

    expect(evaluation.result.state).toBe('error');
    expect(evaluation.proof.status).toBe('error');
    expect(evaluation.result.display).toBe('child-age-under-5: not returned');
    expect(evaluation.result.asOf).toBeUndefined();
  });

  it('returns the server-owned cross-person denial without an upstream call', async () => {
    const fetcher = vi.fn();
    const provider = new LiveEvidenceProvider({}, fetcher);

    const evaluation = await provider.evaluateDetailed(
      { id: 'denial', label: 'Cross-person denial', kind: 'verify' },
      { subject: '2300018263' },
      { scenarioKey: 'denial' }
    );

    expect(fetcher).not.toHaveBeenCalled();
    expect(evaluation.result.reasonCode).toBe('subject_mismatch');
    expect(evaluation.result.authority).toBeUndefined();
    expect(evaluation.proof.authority).toBeUndefined();
    expect(evaluation.proof.headline).toBe(
      'Portal denied the cross-person request before any authority call'
    );
    expect(evaluation.proof.answered).toContain('before any authority call');
    expect(evaluation.raw.response.status).toBe(403);
  });

  it('requires the authority endpoint and purpose-specific token only when evaluated', async () => {
    const missingUrl = new LiveEvidenceProvider(
      { CRA_PENSION_CLIENT_TOKEN: 'cra-pension-token' },
      vi.fn()
    );
    await expect(
      missingUrl.evaluateDetailed(
        { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
        { subject: '2300018263' }
      )
    ).rejects.toThrow('CRA_NOTARY_URL is required');

    const missingToken = new LiveEvidenceProvider(
      { CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org' },
      vi.fn()
    );
    await expect(
      missingToken.evaluateDetailed(
        { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
        { subject: '2300018263' }
      )
    ).rejects.toThrow('CRA_PENSION_CLIENT_TOKEN is required');

    const partialFetcher = vi.fn();
    const incompleteCitizen = new LiveEvidenceProvider(
      {
        CRA_NOTARY_URL: 'https://cra-notary.solmara.registrystack.org',
        CRA_CITIZEN_CLIENT_TOKEN: 'cra-citizen-token',
        NIA_NOTARY_URL: 'https://nia-notary.solmara.registrystack.org'
      },
      partialFetcher
    );
    await expect(
      incompleteCitizen.evaluateDetailed(
        { id: 'citizen-record-status', label: 'Citizen record status', kind: 'verify' },
        { subject: '2300018263' }
      )
    ).rejects.toThrow('NIA_CITIZEN_CLIENT_TOKEN is required');
    expect(partialFetcher).not.toHaveBeenCalled();
  });
});
