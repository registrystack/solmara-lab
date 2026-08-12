import type { AuthorityId } from '$lib/types';

export type SolmaraAuthority = {
  id: AuthorityId;
  label: string;
  serviceId: string;
};

// One Solmara authority source for portal labels, mock provenance, and live
// trace copy. Service endpoints come from environment config; transport security
// is a deployment concern and is not inferred from an evidence response.
export const SOLMARA_AUTHORITIES: Record<AuthorityId, SolmaraAuthority> = {
  civil: {
    id: 'civil',
    label: 'Civil Registration Authority',
    serviceId: 'registry-evidence'
  },
  social: {
    id: 'social',
    label: 'Social Insurance and Pensions Fund',
    serviceId: 'registry-evidence'
  },
  agri: {
    id: 'agri',
    label: 'National Agricultural Data Institute',
    serviceId: 'registry-evidence'
  },
  certs: {
    id: 'certs',
    label: 'Civil Registration Authority',
    serviceId: 'registry-evidence'
  },
  childCivil: {
    id: 'childCivil',
    label: 'Civil Registration Authority',
    serviceId: 'registry-evidence'
  },
  population: {
    id: 'population',
    label: 'National Identity Agency',
    serviceId: 'registry-evidence'
  },
  socialRegistry: {
    id: 'socialRegistry',
    label: 'Social Registry Office',
    serviceId: 'registry-evidence'
  },
  programme: {
    id: 'programme',
    label: 'MoSD Programme MIS',
    serviceId: 'registry-evidence'
  }
};

export const AUTHORITY_NAMES: Record<AuthorityId, string> = Object.fromEntries(
  Object.entries(SOLMARA_AUTHORITIES).map(([id, authority]) => [id, authority.label])
) as Record<AuthorityId, string>;

// A safe default so a wait still names someone if a result omits its authority.
const FALLBACK_AUTHORITY = 'the authority';

export function authorityName(authority: AuthorityId | undefined): string {
  if (authority === undefined) return FALLBACK_AUTHORITY;
  return AUTHORITY_NAMES[authority];
}
