import crypto from "node:crypto";

import { getExecutor } from "./executor";
import { generateRawToken, hashRawToken } from "./tokenHash";
import type { User } from "./types";
import { findUserById, setEmailVerified, updateUserPassword } from "./users";

const VERIFICATION_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours
const RESET_TTL_MS = 60 * 60 * 1000; // 1 hour

export async function createEmailVerificationToken(userId: string): Promise<{ rawToken: string; expiresAt: string }> {
  const db = getExecutor();
  const rawToken = generateRawToken();
  const now = new Date();
  const expiresAt = new Date(now.getTime() + VERIFICATION_TTL_MS).toISOString();
  await db.run("INSERT INTO email_verification_tokens (id, user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)", [
    crypto.randomUUID(),
    userId,
    hashRawToken(rawToken),
    expiresAt,
    now.toISOString(),
  ]);
  return { rawToken, expiresAt };
}

/** Marks the user's email verified and consumes the token in one call.
 * Returns null (never throws) for a missing, expired, or already
 * -consumed token -- the caller decides how to phrase that to the user. */
export async function consumeEmailVerificationToken(rawToken: string): Promise<User | null> {
  const db = getExecutor();
  const tokenHash = hashRawToken(rawToken);
  const row = await db.get<{ id: string; user_id: string; expires_at: string; consumed_at: string | null }>(
    "SELECT * FROM email_verification_tokens WHERE token_hash = ?",
    [tokenHash],
  );
  if (!row || row.consumed_at) return null;
  if (new Date(row.expires_at).getTime() <= Date.now()) return null;

  await db.run("UPDATE email_verification_tokens SET consumed_at = ? WHERE id = ?", [new Date().toISOString(), row.id]);
  await setEmailVerified(row.user_id);
  return findUserById(row.user_id);
}

export async function createPasswordResetToken(userId: string): Promise<{ rawToken: string; expiresAt: string }> {
  const db = getExecutor();
  const rawToken = generateRawToken();
  const now = new Date();
  const expiresAt = new Date(now.getTime() + RESET_TTL_MS).toISOString();
  await db.run("INSERT INTO password_reset_tokens (id, user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?, ?)", [
    crypto.randomUUID(),
    userId,
    hashRawToken(rawToken),
    expiresAt,
    now.toISOString(),
  ]);
  return { rawToken, expiresAt };
}

/** Consumes a password reset token and sets the new (already-hashed)
 * password in one call. Returns null for missing/expired/consumed. */
export async function consumePasswordResetToken(rawToken: string, newPasswordHash: string): Promise<User | null> {
  const db = getExecutor();
  const tokenHash = hashRawToken(rawToken);
  const row = await db.get<{ id: string; user_id: string; expires_at: string; consumed_at: string | null }>(
    "SELECT * FROM password_reset_tokens WHERE token_hash = ?",
    [tokenHash],
  );
  if (!row || row.consumed_at) return null;
  if (new Date(row.expires_at).getTime() <= Date.now()) return null;

  await db.run("UPDATE password_reset_tokens SET consumed_at = ? WHERE id = ?", [new Date().toISOString(), row.id]);
  await updateUserPassword(row.user_id, newPasswordHash);
  return findUserById(row.user_id);
}
