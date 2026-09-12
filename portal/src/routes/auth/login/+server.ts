// GET /auth/login.
//
// In eSignet mode this starts Authorization Code + PKCE and redirects to the
// discovered eSignet authorize endpoint. The default request asks for the
// required business identifier and optional given/family names for display.
// In mock mode it redirects straight to
// the callback, which establishes a server-side persona session. No token is
// forged, stored in the browser, or logged here.

import { error, redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { createEsignetLogin, esignetConfigFor, EsignetConfigError, EsignetAuthError } from '$lib/server/esignet';

export const GET: RequestHandler = async ({ cookies, url }) => {
  try {
    const esignet = esignetConfigFor(url);
    if (esignet) {
      // OIDC backchannel requests use native fetch without the browser request context.
      throw redirect(302, (await createEsignetLogin(cookies, esignet)).toString());
    }
  } catch (err) {
    if (err instanceof EsignetAuthError) throw error(503, 'eSignet login is unavailable');
    if (err instanceof EsignetConfigError) throw error(500, 'eSignet login is not configured');
    throw err;
  }

  // Mock mode: go to callback.
  // A `persona` hint from the visitor center handoff is carried through so the
  // callback can bind that persona's mock session. eSignet mode ignores it: the
  // subject comes from UserInfo, never a query parameter.
  const persona = url.searchParams.get('persona');
  throw redirect(302, persona ? `/auth/callback?persona=${encodeURIComponent(persona)}` : '/auth/callback');
};
