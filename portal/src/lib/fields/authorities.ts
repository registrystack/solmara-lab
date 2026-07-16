import type { NotaryId } from '$lib/types';

export type SolmaraAuthority = {
  id: NotaryId;
  label: string;
  serviceId: string;
};

// One Solmara authority source for portal labels, mock provenance, and live
// trace copy. Service endpoints come from environment config; transport security
// is a deployment concern and is not inferred from an evidence response.
export const SOLMARA_AUTHORITIES: Record<NotaryId, SolmaraAuthority> = {
  civil: {
    id: 'civil',
    label: 'Civil Registration Authority',
    serviceId: 'cra-notary'
  },
  social: {
    id: 'social',
    label: 'Social Insurance and Pensions Fund',
    serviceId: 'sipf-notary'
  },
  agri: {
    id: 'agri',
    label: 'National Agricultural Data Institute',
    serviceId: 'nagdi-notary'
  },
  certs: {
    id: 'certs',
    label: 'Civil Registration Authority',
    serviceId: 'cra-notary'
  },
  childCivil: {
    id: 'childCivil',
    label: 'Civil Registration Authority',
    serviceId: 'cra-notary'
  },
  population: {
    id: 'population',
    label: 'National Identity Agency',
    serviceId: 'nia-notary'
  },
  socialRegistry: {
    id: 'socialRegistry',
    label: 'Social Registry Office',
    serviceId: 'sro-notary'
  },
  programme: {
    id: 'programme',
    label: 'MoSD Programme MIS',
    serviceId: 'programme-notary'
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
