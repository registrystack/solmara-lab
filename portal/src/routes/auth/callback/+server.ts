// GET /auth/callback.
//
// Establishes a server-side persona session for the mock login. No token is
// forged, stored in the browser, or logged here.

import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { setMockSession } from '$lib/server/session';
import { resolvePersona } from '$lib/server/personas';

export const GET: RequestHandler = ({ cookies, url }) => {
  // Set a subject-bound mock session and continue to the catalog. A valid
  // persona hint from the visitor center binds that persona; an unknown or
  // absent hint falls back to the default Elena Dela Cruz session, so a query
  // parameter can never forge a session for someone off the published roster.
  const persona = resolvePersona(url.searchParams.get('persona'));
  setMockSession(cookies, persona ?? undefined);
  throw redirect(302, '/services');
};
