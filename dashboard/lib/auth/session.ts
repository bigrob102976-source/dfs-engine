import { cookies } from "next/headers";

import { createSession, deleteSessionByRawToken, findSessionByRawToken } from "@/lib/db/sessions";
import type { User } from "@/lib/db/types";

// Milestone 21: real per-user session cookie, replacing the old
// dfs_dashboard_session single-shared-password cookie. The cookie holds
// only a random opaque token; the user's role is NEVER encoded in it --
// getCurrentUser() always re-reads the role fresh from the sessions ->
// users join in lib/db/sessions.ts.
export const SESSION_COOKIE = "bigmoney_session";
const SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60; // 30 days

export interface CurrentUser {
  id: string;
  email: string;
  role: string;
  displayName: string | null;
  emailVerifiedAt: string | null;
}

function toCurrentUser(user: User): CurrentUser {
  return {
    id: user.id,
    email: user.email,
    role: user.role,
    displayName: user.display_name,
    emailVerifiedAt: user.email_verified_at,
  };
}

/** Server Action / Route Handler only (mutates cookies). Creates a new
 * DB session row and sets the cookie. */
export async function establishSession(userId: string, userAgent: string | null): Promise<void> {
  const { rawToken } = createSession(userId, userAgent);
  const store = await cookies();
  store.set(SESSION_COOKIE, rawToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
}

/** Safe to call from Server Components, layouts, Route Handlers, or
 * Server Actions -- read-only, never mutates the cookie jar (Next.js
 * only allows cookie mutation from Server Actions/Route Handlers, and
 * this needs to work everywhere authorization is checked). A missing,
 * expired, or forged/tampered token simply resolves to null; the stale
 * cookie (if any) is left alone here and overwritten on the next real
 * login, or explicitly cleared by destroySession(). */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  const store = await cookies();
  const rawToken = store.get(SESSION_COOKIE)?.value;
  if (!rawToken) return null;
  const result = findSessionByRawToken(rawToken);
  if (!result) return null;
  return toCurrentUser(result.user);
}

/** Server Action / Route Handler only (mutates cookies). Deletes the
 * current session row (if any) and clears the cookie. */
export async function destroySession(): Promise<void> {
  const store = await cookies();
  const rawToken = store.get(SESSION_COOKIE)?.value;
  if (rawToken) deleteSessionByRawToken(rawToken);
  store.delete(SESSION_COOKIE);
}
