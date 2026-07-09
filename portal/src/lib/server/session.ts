// Server-side portal sessions. Mock mode binds a canned/persona subject without
// eSignet; eSignet mode binds the subject returned by UserInfo. The session
// shape stays the same in both modes.
//
// We NEVER forge or store a token here: a mock session carries only the subject
// and display name, never bearer material. In eSignet mode the BFF derives the
// same session shape from UserInfo and does not store access tokens here.
// Server-only module.

import type { Cookies } from '@sveltejs/kit';
import { randomUUID } from 'node:crypto';
import { PERSONA } from '$lib/providers/mock';

export type PortalSession = {
  subject: string; // Solmara UIN bound server-side, e.g. 2300010248
  displayName: string; // from eSignet UserInfo in Phase 1; canned here
};

export const SESSION_COOKIE = 'solmara_session';
const SESSION_MAX_AGE_SECONDS = 60 * 60;
const SESSION_MAX_AGE_MS = SESSION_MAX_AGE_SECONDS * 1000;

// The single canned Phase 0 session. Elena Dela Cruz, 2300018263.
export const MOCK_SESSION: PortalSession = {
  subject: PERSONA.elena,
  displayName: 'Elena Dela Cruz'
};

type StoredSession = {
  session: PortalSession;
  expiresAt: number;
};

const sessions = new Map<string, StoredSession>();

// Establish the mock session cookie. httpOnly so the browser script never reads
// it; no token material is stored. Phase 1 stores the eSignet session server-side
// keyed by an opaque id instead of carrying the subject in the cookie value.
//
// The optional `session` selects which mock persona to bind. It defaults to the
// canned Elena Dela Cruz session. Callers pass a persona ONLY after validating
// it against the published roster (see `personas.ts`); the subject is still
// bound server-side, never read from the cookie value.
export function setPortalSession(cookies: Cookies, session: PortalSession): void {
  reclaimExpiredSessions();
  const sessionId = randomUUID();
  sessions.set(sessionId, {
    session,
    expiresAt: Date.now() + SESSION_MAX_AGE_MS
  });
  cookies.set(SESSION_COOKIE, sessionId, {
    path: '/',
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.PORTAL_SECURE_COOKIES === 'true',
    maxAge: SESSION_MAX_AGE_SECONDS
  });
}

export function setMockSession(cookies: Cookies, session: PortalSession = MOCK_SESSION): void {
  setPortalSession(cookies, session);
}

export function getSessionId(cookies: Cookies): string | null {
  reclaimExpiredSessions();
  const sessionId = cookies.get(SESSION_COOKIE);
  if (!sessionId || !sessions.has(sessionId)) return null;
  return sessionId;
}

// Resolve the session subject SERVER-SIDE. The BFF binds evaluations to this, so
// a client-supplied target is never trusted. Returns null when unauthenticated.
export function getSession(cookies: Cookies): PortalSession | null {
  const sessionId = getSessionId(cookies);
  return sessionId ? sessions.get(sessionId)?.session ?? null : null;
}

export function clearSession(cookies: Cookies): void {
  const sessionId = cookies.get(SESSION_COOKIE);
  if (sessionId) sessions.delete(sessionId);
  cookies.delete(SESSION_COOKIE, { path: '/' });
}

export function resetMockSessions(): void {
  sessions.clear();
}

export function reclaimExpiredSessions(now = Date.now()): number {
  let reclaimed = 0;
  for (const [sessionId, stored] of sessions) {
    if (stored.expiresAt <= now) {
      sessions.delete(sessionId);
      reclaimed += 1;
    }
  }
  return reclaimed;
}
