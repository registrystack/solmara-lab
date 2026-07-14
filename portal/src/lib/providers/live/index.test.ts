import { describe, expect, it, vi } from 'vitest';
import { LiveEvidenceProvider } from '.';
import { PURPOSES } from '$lib/forms/descriptors';
import { FEDERATED_PREDICATE_BUNDLE_FORMAT } from '$lib/providers/mock/wire';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' }
  });
}

describe('LiveEvidenceProvider', () => {
  it('constructs Solmara Relay and Notary calls from environment config', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ catalog: 'ok' }))
      .mockResolvedValueOnce(
        jsonResponse({
          results: [
            {
              claim_id: 'person-is-deceased',
              claim_version: '2026-07',
              disclosure: 'predicate',
              evaluation_id: 'live-1',
              issued_at: '2026-07-04T00:00:00Z',
              satisfied: true,
              value: true
            }
          ]
        })
      );
    const provider = new LiveEvidenceProvider(
      {
        PORTAL_CITIZEN_NOTARY_URL: 'https://citizen-notary.solmara.registrystack.org',
        PORTAL_CITIZEN_NOTARY_TOKEN: 'notary-token',
        PENSION_NOTARY_URL: 'https://pension-notary.solmara.registrystack.org',
        PENSION_NOTARY_TOKEN: 'pension-token',
        PORTAL_RELAY_TOKEN: 'relay-token',
        PORTAL_AGRI_RELAY_URL: 'https://nagdi-relay.solmara.registrystack.org',
        PORTAL_CIVIL_RELAY_URL: 'https://civil-relay.solmara.registrystack.org',
        PORTAL_SOCIAL_RELAY_URL: 'https://social-relay.solmara.registrystack.org',
        PORTAL_CERTS_RELAY_URL: 'https://civil-relay.solmara.registrystack.org'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
      { subject: '2300010248' }
    );

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0][0]).toBe('https://civil-relay.solmara.registrystack.org/metadata/catalog');
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      method: 'GET',
      headers: {
        Authorization: 'Bearer relay-token',
        'Data-Purpose': PURPOSES.pensionPaymentReview
      }
    });
    expect(fetcher.mock.calls[1][0]).toBe('https://pension-notary.solmara.registrystack.org/v1/evaluations');
    const notaryInit = fetcher.mock.calls[1][1] as RequestInit;
    expect(notaryInit.headers).toMatchObject({
      'x-api-key': 'pension-token',
      'Data-Purpose': PURPOSES.pensionPaymentReview,
      'Content-Type': 'application/json'
    });
    expect(JSON.parse(String(notaryInit.body))).toMatchObject({
      claims: [{ id: 'person-is-deceased', version: '2026-07' }],
      purpose: PURPOSES.pensionPaymentReview,
      target: { identifiers: [{ scheme: 'solmara_uin', value: '2300010248' }] }
    });
    expect(evaluation.result.display).toBe('Death registered: yes');
    expect(evaluation.raw.response.status).toBe(200);
  });

  it('uses only a server-selected story subject to target fixture personas', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ catalog: 'ok' }))
      .mockResolvedValueOnce(jsonResponse({ results: [{ satisfied: true, value: true }] }));
    const provider = new LiveEvidenceProvider(
      {
        PENSION_NOTARY_URL: 'https://pension-notary.solmara.registrystack.org',
        PENSION_NOTARY_TOKEN: 'pension-token',
        PORTAL_RELAY_TOKEN: 'relay-token',
        PORTAL_CIVIL_RELAY_URL: 'https://civil-relay.solmara.registrystack.org',
        PORTAL_SOCIAL_RELAY_URL: 'https://social-relay.solmara.registrystack.org',
        PORTAL_AGRI_RELAY_URL: 'https://nagdi-relay.solmara.registrystack.org',
        PORTAL_CERTS_RELAY_URL: 'https://civil-relay.solmara.registrystack.org'
      },
      fetcher
    );

    await provider.evaluateDetailed(
      { id: 'person-is-alive', label: 'Alive?', kind: 'verify' },
      { subject: '2300018263', selectedSubject: '2300109568' }
    );

    const notaryInit = fetcher.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(String(notaryInit.body))).toMatchObject({
      target: { identifiers: [{ scheme: 'solmara_uin', value: '2300109568' }] }
    });
  });

  it('denies delegated live reads before any upstream call unless the guardian link is proven', async () => {
    const fetcher = vi.fn();
    const provider = new LiveEvidenceProvider(
      {
        CHILD_BENEFIT_FEDERATOR_URL: 'https://child-benefit-federator.solmara.registrystack.org',
        CHILD_BENEFIT_FEDERATOR_TOKEN: 'child-token',
        PORTAL_RELAY_TOKEN: 'relay-token',
        PORTAL_CIVIL_RELAY_URL: 'https://civil-relay.solmara.registrystack.org',
        PORTAL_SOCIAL_RELAY_URL: 'https://social-relay.solmara.registrystack.org',
        PORTAL_AGRI_RELAY_URL: 'https://nagdi-relay.solmara.registrystack.org',
        PORTAL_CERTS_RELAY_URL: 'https://civil-relay.solmara.registrystack.org'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      { subject: '2300018263', delegatedTarget: '2300010248' }
    );

    expect(fetcher).not.toHaveBeenCalled();
    expect(evaluation.raw.response.status).toBe(403);
    expect(evaluation.result.reasonCode).toBe('relationship_not_proven');
  });

  it('sends delegated live reads for the server-selected dependent after the server-side gate', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ claims: [{ id: 'child-age-under-5' }] }))
      .mockResolvedValueOnce(
        jsonResponse({
          schema_version: 'solmara-child-benefit-federator/v1',
          bundle_id: 'fcb_live_1',
          federator: {
            service_id: 'child-benefit-federator',
            issuer: 'https://child-benefit-federator.solmara.registrystack.org',
            decision: 'not_composed'
          },
          results: [
            {
              claim_id: 'child-age-under-5',
              claim_version: '2026-07',
              issued_at: '2026-07-14T00:00:00Z',
              satisfied: true,
              value: true,
              authority: 'Civil Registration Authority',
              notary_service_id: 'civil-child-benefit-notary'
            }
          ],
          federation_trace: []
        })
      );
    const provider = new LiveEvidenceProvider(
      {
        CHILD_BENEFIT_FEDERATOR_URL: 'https://child-benefit-federator.solmara.registrystack.org',
        CHILD_BENEFIT_FEDERATOR_TOKEN: 'child-token',
        PORTAL_RELAY_TOKEN: 'relay-token',
        PORTAL_CIVIL_RELAY_URL: 'https://civil-relay.solmara.registrystack.org',
        PORTAL_SOCIAL_RELAY_URL: 'https://social-relay.solmara.registrystack.org',
        PORTAL_AGRI_RELAY_URL: 'https://nagdi-relay.solmara.registrystack.org',
        PORTAL_CERTS_RELAY_URL: 'https://civil-relay.solmara.registrystack.org'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'date-of-birth', label: 'Child age under 5', kind: 'verify' },
      { subject: '2300018263', delegatedTarget: '2300010248' },
      { guardianLinkVerified: true }
    );

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls[0]).toEqual([
      'https://child-benefit-federator.solmara.registrystack.org/v1/claims',
      {
        method: 'GET',
        headers: {
          'x-api-key': 'child-token',
          Accept: 'application/json',
          'Data-Purpose': PURPOSES.childBenefitReview
        }
      }
    ]);
    expect(fetcher.mock.calls[1][0]).toBe(
      'https://child-benefit-federator.solmara.registrystack.org/v1/evaluations'
    );
    const notaryInit = fetcher.mock.calls[1][1] as RequestInit;
    expect(notaryInit.headers).toEqual({
      'x-api-key': 'child-token',
      Accept: FEDERATED_PREDICATE_BUNDLE_FORMAT,
      'Data-Purpose': PURPOSES.childBenefitReview,
      'Content-Type': 'application/json'
    });
    const body = JSON.parse(String(notaryInit.body));
    expect(body).toEqual({
      target: {
        type: 'Person',
        identifiers: [{ scheme: 'solmara_uin', value: '2300010248' }]
      },
      claims: ['child-age-under-5'],
      disclosure: 'predicate',
      format: FEDERATED_PREDICATE_BUNDLE_FORMAT
    });
    expect(body).not.toHaveProperty('purpose');
    expect(body).not.toHaveProperty('relationship');
    expect(body.on_behalf_of).toBeUndefined();
    expect(evaluation.proof.crypto).toEqual({
      signedBy: 'Civil Registration Authority source-owned Notary',
      algorithm: 'EdDSA-Ed25519 authority response JWT verified by the federator',
      issuerKey:
        'did:web:civil-child-benefit-notary.solmara.registrystack.org#federation-key-1',
      holderBound: 'Purpose- and subject-bound child-benefit federation request',
      credential: 'Federated predicate bundle',
      auditId: 'bundle:fcb_live_1'
    });
    expect(JSON.stringify(evaluation.proof.crypto)).not.toContain('SD-JWT');
    expect(JSON.stringify(evaluation.proof.crypto)).not.toContain('notary:citizen');
  });

  it('returns the server-owned denial set piece without an upstream source call', async () => {
    const fetcher = vi.fn();
    const provider = new LiveEvidenceProvider(
      {
        PENSION_NOTARY_URL: 'https://pension-notary.solmara.registrystack.org',
        PENSION_NOTARY_TOKEN: 'pension-token',
        PORTAL_RELAY_TOKEN: 'relay-token',
        PORTAL_CIVIL_RELAY_URL: 'https://civil-relay.solmara.registrystack.org',
        PORTAL_SOCIAL_RELAY_URL: 'https://social-relay.solmara.registrystack.org',
        PORTAL_AGRI_RELAY_URL: 'https://nagdi-relay.solmara.registrystack.org',
        PORTAL_CERTS_RELAY_URL: 'https://civil-relay.solmara.registrystack.org'
      },
      fetcher
    );

    const evaluation = await provider.evaluateDetailed(
      { id: 'denial', label: 'Cross-person denial', kind: 'verify' },
      { subject: '2300018263' },
      { scenarioKey: 'denial' }
    );

    expect(fetcher).not.toHaveBeenCalled();
    expect(evaluation.result.reasonCode).toBe('subject_mismatch');
    expect(evaluation.raw.response.status).toBe(403);
  });

  it('requires explicit live endpoint configuration for the evaluated service', async () => {
    const provider = new LiveEvidenceProvider(
      {
        PORTAL_CITIZEN_NOTARY_TOKEN: 'token',
        PORTAL_RELAY_TOKEN: 'relay-token',
        PORTAL_CIVIL_RELAY_URL: 'https://civil-relay.solmara.registrystack.org',
        PORTAL_SOCIAL_RELAY_URL: 'https://social-relay.solmara.registrystack.org',
        PORTAL_AGRI_RELAY_URL: 'https://nagdi-relay.solmara.registrystack.org',
        PORTAL_CERTS_RELAY_URL: 'https://civil-relay.solmara.registrystack.org'
      },
      vi.fn()
    );
    await expect(
      provider.evaluateDetailed({ id: 'person-is-alive', label: 'Alive?', kind: 'verify' }, { subject: '2300018263' })
    ).rejects.toThrow('PENSION_NOTARY_URL is required');
  });
});
