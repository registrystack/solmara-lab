import { resolvePersona } from '$lib/server/personas';
import type { PageServerLoad } from './$types';

// Read the persona handoff hint from the visitor center and validate it against
// the published roster server-side. Only a known persona is forwarded to the
// mock sign-in; an unknown hint is dropped so the default session is used.
export const load: PageServerLoad = ({ url }) => {
  const persona = resolvePersona(url.searchParams.get('persona'));
  return {
    persona: persona?.subject ?? null,
    personaName: persona?.displayName ?? null
  };
};
