import crypto from "node:crypto";

import { getExecutor } from "./executor";
import { generateRawToken, hashRawToken } from "./tokenHash";
import type { User } from "./types";
import { findUserById } from "./users";

const SESSION_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

export async function createSession(userId: string, userAgent: string | null): Promise<{ rawToken: string; expiresAt: string }> {
  const db = getExecutor();
  const rawToken = generateRawToken();
  const now = new Date();
  const expiresAt = new Date(now.getTime() + SESSION_TTL_MS).toISOString();
  await db.run("INSERT INTO sessions (id, token_hash, user_id, user_agent, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)", [
    crypto.randomUUID(),
    hashRawToken(rawToken),
    userId,
    userAgent,
    now.toISOString(),
    expiresAt,
  ]);
  return { rawToken, expiresAt };
}

/** Resolves a raw session token (as read from the cookie) to its user,
 * or null if the token doesn't match any session, or the session has
 * expired. This is the ONLY path by which a request's identity is
 * established -- the role on the returned user is a fresh row straight
 * from the users table, never anything cached in the token/cookie
 * itself. Expired sessions are opportunistically deleted. */
export async function findSessionByRawToken(rawToken: string): Promise<{ user: User } | null> {
  const db = getExecutor();
  const tokenHash = hashRawToken(rawToken);
  const session = await db.get<{ id: string; user_id: string; expires_at: string }>("SELECT * FROM sessions WHERE token_hash = ?", [
    tokenHash,
  ]);
  if (!session) return null;

  if (new Date(session.expires_at).getTime() <= Date.now()) {
    await db.run("DELETE FROM sessions WHERE id = ?", [session.id]);
    return null;
  }

  const user = await findUserById(session.user_id);
  if (!user || user.disabled_at) return null;
  return { user };
}

export async function deleteSessionByRawToken(rawToken: string): Promise<void> {
  const db = getExecutor();
  await db.run("DELETE FROM sessions WHERE token_hash = ?", [hashRawToken(rawToken)]);
}

export async function deleteAllSessionsForUser(userId: string): Promise<void> {
  const db = getExecutor();
  await db.run("DELETE FROM sessions WHERE user_id = ?", [userId]);
}
