// GET /auth/login.
//
// The portal signs in with its mock login: this redirects straight to the
// callback, which establishes a server-side persona session. No token is
// forged, stored in the browser, or logged here.

import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = ({ url }) => {
  // A `persona` hint from the visitor center handoff is carried through so the
  // callback can bind that persona's mock session.
  const persona = url.searchParams.get('persona');
  throw redirect(302, persona ? `/auth/callback?persona=${encodeURIComponent(persona)}` : '/auth/callback');
};
