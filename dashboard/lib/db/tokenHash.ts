import crypto from "node:crypto";

/** SHA-256 hex digest of a raw token -- used for session tokens, email
 * verification tokens, and password reset tokens alike. These tokens
 * already carry 256 bits of their own entropy (crypto.randomBytes), so
 * a fast cryptographic hash (not a slow, salted password-stretching
 * hash) is the correct primitive here: the goal is "don't store the
 * usable secret at rest," not "resist offline brute force of a
 * low-entropy value" (that's what lib/auth/password.ts's scrypt is
 * for). The raw token itself lives only in the cookie / the one-time
 * link shown to the user, never in the database. */
export function hashRawToken(rawToken: string): string {
  return crypto.createHash("sha256").update(rawToken).digest("hex");
}

export function generateRawToken(): string {
  return crypto.randomBytes(32).toString("hex");
}
