import { describe, expect, it } from 'vitest';
import { hasExpectedSuccessfulClaims, isExpectedProblemDenial } from './runresult';
import type { StepRunResult } from './types';

const expectedClaims = [
  'birth-is-registered',
  'population-record-active',
  'child-age-under-5',
  'household-below-poverty-threshold',
  'not-already-enrolled'
];

function result(
  overrides: {
    friendlyStatus?: string;
    httpStatus?: number;
    claims?: { claim_id: string; satisfied: boolean }[];
    body?: Record<string, unknown>;
  } = {}
): StepRunResult {
  return {
    step_id: 'positive',
    friendly: {
      title: 'Evidence returned.',
      message: 'The expected answers were returned.',
      status: overrides.friendlyStatus ?? 'done',
      facts: []
    },
    request_source: {
      method: 'POST',
      url: 'http://scenario-runner/v1/evaluations',
      headers: {}
    },
    response_source: {
      status: overrides.httpStatus ?? 200,
      body:
        overrides.body ??
        {
          results:
            overrides.claims ??
            expectedClaims.map((claim_id) => ({ claim_id, satisfied: true }))
        }
    }
  };
}

describe('hasExpectedSuccessfulClaims', () => {
  it('accepts a completed 2xx response with exactly the expected satisfied claims', () => {
    expect(hasExpectedSuccessfulClaims(result(), expectedClaims)).toBe(true);
  });

  it('rejects a needs-attention result even when a response object exists', () => {
    expect(
      hasExpectedSuccessfulClaims(
        result({ friendlyStatus: 'needs_attention', httpStatus: 503, claims: [] }),
        expectedClaims
      )
    ).toBe(false);
  });

  it('rejects partial or unsatisfied evidence', () => {
    expect(
      hasExpectedSuccessfulClaims(
        result({
          claims: expectedClaims.slice(0, 4).map((claim_id) => ({ claim_id, satisfied: true }))
        }),
        expectedClaims
      )
    ).toBe(false);
    expect(
      hasExpectedSuccessfulClaims(
        result({
          claims: expectedClaims.map((claim_id, index) => ({
            claim_id,
            satisfied: index !== 2
          }))
        }),
        expectedClaims
      )
    ).toBe(false);
  });

  it('rejects duplicated or unexpected claims', () => {
    expect(
      hasExpectedSuccessfulClaims(
        result({
          claims: [
            ...expectedClaims.slice(0, 4).map((claim_id) => ({ claim_id, satisfied: true })),
            { claim_id: expectedClaims[0], satisfied: true }
          ]
        }),
        expectedClaims
      )
    ).toBe(false);
    expect(
      hasExpectedSuccessfulClaims(
        result({
          claims: [
            ...expectedClaims.slice(0, 4).map((claim_id) => ({ claim_id, satisfied: true })),
            { claim_id: 'unexpected-disclosure', satisfied: true }
          ]
        }),
        expectedClaims
      )
    ).toBe(false);
  });
});

describe('isExpectedProblemDenial', () => {
  it('accepts only an explicit matching policy code returned with HTTP 403', () => {
    expect(
      isExpectedProblemDenial(
        result({
          friendlyStatus: 'done',
          httpStatus: 403,
          body: { code: 'pdp.purpose_not_permitted' }
        }),
        'pdp.purpose_not_permitted'
      )
    ).toBe(true);
  });

  it('rejects authentication errors, server errors, and synthesized codes', () => {
    for (const candidate of [
      result({
        friendlyStatus: 'needs_attention',
        httpStatus: 401,
        body: { code: 'auth.invalid_token' }
      }),
      result({
        friendlyStatus: 'needs_attention',
        httpStatus: 503,
        body: { code: 'authority.unavailable' }
      }),
      result({
        friendlyStatus: 'needs_attention',
        httpStatus: 403,
        body: {}
      })
    ]) {
      expect(isExpectedProblemDenial(candidate, 'pdp.purpose_not_permitted')).toBe(false);
    }
  });
});
