import type { AuthorityId, EvidencePresentation, EvidenceSource } from '$lib/types';

export type SolmaraAuthority = {
  id: AuthorityId;
  label: string;
  serviceId: string;
  issuer: string;
  origin: string;
};

// One Solmara authority source for portal labels, mock provenance, and live
// trace copy. Service endpoints come from environment config; transport security
// is a deployment concern and is not inferred from an evidence response.
export const SOLMARA_AUTHORITIES: Record<AuthorityId, SolmaraAuthority> = {
  civil: {
    id: 'civil',
    label: 'Civil Registration Authority',
    serviceId: 'cra-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:cra',
    origin: 'https://cra-evidence.solmara.registrystack.org'
  },
  social: {
    id: 'social',
    label: 'Social Insurance and Pensions Fund',
    serviceId: 'sipf-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:sipf',
    origin: 'https://sipf-evidence.solmara.registrystack.org'
  },
  agri: {
    id: 'agri',
    label: 'National Agricultural Data Institute',
    serviceId: 'nagdi-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:nagdi',
    origin: 'https://nagdi-evidence.solmara.registrystack.org'
  },
  certs: {
    id: 'certs',
    label: 'Civil Registration Authority',
    serviceId: 'cra-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:cra',
    origin: 'https://cra-evidence.solmara.registrystack.org'
  },
  childCivil: {
    id: 'childCivil',
    label: 'Civil Registration Authority',
    serviceId: 'cra-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:cra',
    origin: 'https://cra-evidence.solmara.registrystack.org'
  },
  population: {
    id: 'population',
    label: 'National Identity Agency',
    serviceId: 'nia-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:nia',
    origin: 'https://nia-evidence.solmara.registrystack.org'
  },
  socialRegistry: {
    id: 'socialRegistry',
    label: 'Social Registry Office',
    serviceId: 'sro-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:sro',
    origin: 'https://sro-evidence.solmara.registrystack.org'
  },
  programme: {
    id: 'programme',
    label: 'MoSD Programme MIS',
    serviceId: 'mosd-programme-evidence',
    issuer: 'did:web:id.registrystack.org:solmara:authority:mosd-programme-mis',
    origin: 'https://mosd-programme-evidence.solmara.registrystack.org'
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

export function evidencePresentation(
  authority: AuthorityId,
  source: EvidenceSource
): EvidencePresentation {
  const definition = SOLMARA_AUTHORITIES[authority];
  return {
    authority: definition.label,
    issuer: definition.issuer,
    serviceId: definition.serviceId,
    source
  };
}
