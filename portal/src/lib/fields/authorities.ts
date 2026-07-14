import type { NotaryId } from '$lib/types';

export type SolmaraAuthority = {
  id: NotaryId;
  label: string;
  serviceId: string;
  issuerKey: string;
};

// One Solmara authority source for portal labels, mock provenance, and live
// trace copy. Service endpoints use real TLS hosts from environment config.
export const SOLMARA_AUTHORITIES: Record<NotaryId, SolmaraAuthority> = {
  civil: {
    id: 'civil',
    label: 'Civil Registration Authority',
    serviceId: 'citizen-notary',
    issuerKey: 'did:web:id.registrystack.org:solmara:notary:citizen#key-1'
  },
  social: {
    id: 'social',
    label: 'Ministry of Social Development',
    serviceId: 'citizen-notary',
    issuerKey: 'did:web:id.registrystack.org:solmara:notary:citizen#key-1'
  },
  agri: {
    id: 'agri',
    label: 'National Agricultural Data Institute',
    serviceId: 'citizen-notary',
    issuerKey: 'did:web:id.registrystack.org:solmara:notary:citizen#key-1'
  },
  certs: {
    id: 'certs',
    label: 'Civil Registration Authority',
    serviceId: 'citizen-notary',
    issuerKey: 'did:web:id.registrystack.org:solmara:notary:citizen#key-1'
  },
  childCivil: {
    id: 'childCivil',
    label: 'Civil Registration Authority',
    serviceId: 'civil-child-benefit-notary',
    issuerKey:
      'did:web:civil-child-benefit-notary.solmara.registrystack.org#federation-key-1'
  },
  population: {
    id: 'population',
    label: 'National Identity Agency',
    serviceId: 'nia-child-benefit-notary',
    issuerKey:
      'did:web:nia-child-benefit-notary.solmara.registrystack.org#federation-key-1'
  },
  socialRegistry: {
    id: 'socialRegistry',
    label: 'Social Registry Office',
    serviceId: 'sro-child-benefit-notary',
    issuerKey:
      'did:web:sro-child-benefit-notary.solmara.registrystack.org#federation-key-1'
  },
  programme: {
    id: 'programme',
    label: 'MoSD Programme MIS',
    serviceId: 'programme-child-benefit-notary',
    issuerKey:
      'did:web:programme-child-benefit-notary.solmara.registrystack.org#federation-key-1'
  }
};

export const AUTHORITY_NAMES: Record<NotaryId, string> = Object.fromEntries(
  Object.entries(SOLMARA_AUTHORITIES).map(([id, authority]) => [id, authority.label])
) as Record<NotaryId, string>;

// A safe default so a wait still names *someone* if a result omits its notary.
const FALLBACK_AUTHORITY = 'the authority';

export function authorityName(notary: NotaryId | undefined): string {
  if (notary === undefined) return FALLBACK_AUTHORITY;
  return AUTHORITY_NAMES[notary];
}
