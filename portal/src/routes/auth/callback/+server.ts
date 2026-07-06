// GET /auth/callback : MOCK-ONLY callback stub for Phase 0.
//
// Phase 1 replaces this with the real eSignet code exchange: read ?code + ?state,
// verify the PKCE verifier stored at /auth/login, exchange the code with
// private-key-jwt (the client private key stays server-side, never shipped to the
// browser, never logged), keep the access/ID token + UserInfo in a server session
// cookie, and prefill identity from UserInfo. The browser never sees raw tokens.
//
// For Phase 0 this establishes the canned Elena Dela Cruz (2300018263) session WITHOUT
// real eSignet so the mock provider has a server-bound subject. No token is ever
// forged, stored, or logged.

import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { setMockSession } from '$lib/server/session';
import { resolvePersona } from '$lib/server/personas';

export const GET: RequestHandler = ({ cookies, url }) => {
  // Phase 1: exchange ?code, verify PKCE, store tokens + UserInfo server-side.
  // Phase 0: set a subject-bound mock session and continue to the catalog. A
  // valid persona hint from the visitor center binds that persona; an unknown or
  // absent hint falls back to the default Elena Dela Cruz session, so a query
  // parameter can never forge a session for someone off the published roster.
  const persona = resolvePersona(url.searchParams.get('persona'));
  setMockSession(cookies, persona ?? undefined);
  throw redirect(302, '/services');
};
