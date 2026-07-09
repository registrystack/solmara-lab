// GET /auth/login.
//
// In eSignet mode this starts Authorization Code + PKCE and redirects to the
// configured eSignet authorize endpoint. In mock mode it redirects straight to
// the callback, which establishes a server-side persona session. No token is
// forged, stored in the browser, or logged here.

import { error, redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { createEsignetLogin, esignetConfigFor, EsignetConfigError } from '$lib/server/esignet';

export const GET: RequestHandler = ({ cookies, url }) => {
  try {
    const esignet = esignetConfigFor(url);
    if (esignet) {
      throw redirect(302, createEsignetLogin(cookies, esignet).toString());
    }
  } catch (err) {
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
