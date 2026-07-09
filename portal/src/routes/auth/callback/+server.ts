// GET /auth/callback.
//
// In eSignet mode this verifies login state, exchanges the code with
// private-key JWT, fetches UserInfo, and stores only the derived subject/display
// name in the server-side portal session. In mock mode it establishes a
// server-side persona session. No token is forged, stored in the browser, or
// logged here.

import { error, redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { completeEsignetLogin, esignetConfigFor, EsignetAuthError, EsignetConfigError } from '$lib/server/esignet';
import { setMockSession, setPortalSession } from '$lib/server/session';
import { resolvePersona } from '$lib/server/personas';

export const GET: RequestHandler = async ({ cookies, fetch, url }) => {
  try {
    const esignet = esignetConfigFor(url);
    if (esignet) {
      const session = await completeEsignetLogin(cookies, url, esignet, fetch);
      setPortalSession(cookies, session);
      throw redirect(302, '/services');
    }
  } catch (err) {
    if (err instanceof EsignetConfigError) throw error(500, 'eSignet login is not configured');
    if (err instanceof EsignetAuthError) throw error(401, 'eSignet login failed');
    throw err;
  }

  // Mock mode: set a subject-bound mock session and continue to the catalog. A
  // valid persona hint from the visitor center binds that persona; an unknown or
  // absent hint falls back to the default Elena Dela Cruz session, so a query
  // parameter can never forge a session for someone off the published roster.
  const persona = resolvePersona(url.searchParams.get('persona'));
  setMockSession(cookies, persona ?? undefined);
  throw redirect(302, '/services');
};
