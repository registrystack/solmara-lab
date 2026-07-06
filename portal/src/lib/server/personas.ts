// MOCK-ONLY persona roster for the Phase 0 handoff from the visitor center.
//
// The visitor center's persona cards link to `/?persona=<UIN>`. In Phase 1 the
// login is a real eSignet flow and this file goes away: the subject comes from
// UserInfo, never from a query parameter. For Phase 0 we accept a persona hint
// ONLY when it matches this published, synthetic roster, so a stranger UIN can
// never forge a session for someone off the cast list. Everything here is
// synthetic Solmara data.

import type { PortalSession } from './session';

// UIN -> display name. These are the fixed, published personas the visitor
// center surfaces (the first rows of the generated persona roster).
export const KNOWN_PERSONAS: Record<string, string> = {
  '2300010248': 'Mateo Santos',
  '2300018263': 'Elena Dela Cruz',
  '2300027390': 'Luis Okafor',
  '2300036523': 'Hana Aquino',
  '2300045650': 'Priya Mensah',
  '2300054788': 'Tomas Bello',
  '2300063915': 'Joana Bello',
  '2300073046': 'Karim Kone'
};

/**
 * Resolve a persona hint to a mock session, or null when the UIN is not on the
 * published roster. A null result means the caller should fall back to the
 * default mock session rather than trust the hint.
 */
export function resolvePersona(uin: string | null | undefined): PortalSession | null {
  if (!uin) return null;
  const displayName = KNOWN_PERSONAS[uin];
  return displayName ? { subject: uin, displayName } : null;
}
