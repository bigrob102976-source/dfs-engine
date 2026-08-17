import crypto from "node:crypto";

import { getDb } from "./client";
import { generateRawToken, hashRawToken } from "./tokenHash";
import type { User } from "./types";
import { findUserById } from "./users";

const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

export function createSession(userId: string, userAgent: string | null): { rawToken: string; expiresAt: string } {
  const db = getDb();
  const rawToken = generateRawToken();
  const now = new Date();
  const expiresAt = new Date(now.getTime() + SESSION_TTL_MS).toISOString();
  db.prepare(
    "INSERT INTO sessions (id, token_hash, user_id, user_agent, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
  ).run(crypto.randomUUID(), hashRawToken(rawToken), userId, userAgent, now.toISOString(), expiresAt);
  return { rawToken, expiresAt };
}

/** Resolves a raw session token (as read from the cookie) to its user,
 * or null if the token doesn't match any session, or the session has
 * expired. This is the ONLY path by which a request's identity is
 * established -- the role on the returned user is a fresh row straight
 * from the users table, never anything cached in the token/cookie
 * itself. Expired sessions are opportunistically deleted. */
export function findSessionByRawToken(rawToken: string): { user: User } | null {
  const db = getDb();
  const tokenHash = hashRawToken(rawToken);
  const session = db.prepare("SELECT * FROM sessions WHERE token_hash = ?").get(tokenHash) as
    | { id: string; user_id: string; expires_at: string }
    | undefined;
  if (!session) return null;

  if (new Date(session.expires_at).getTime() <= Date.now()) {
    db.prepare("DELETE FROM sessions WHERE id = ?").run(session.id);
    return null;
  }

  const user = findUserById(session.user_id);
  if (!user || user.disabled_at) return null;
  return { user };
}

export function deleteSessionByRawToken(rawToken: string): void {
  const db = getDb();
  db.prepare("DELETE FROM sessions WHERE token_hash = ?").run(hashRawToken(rawToken));
}

export function deleteAllSessionsForUser(userId: string): void {
  const db = getDb();
  db.prepare("DELETE FROM sessions WHERE user_id = ?").run(userId);
}
