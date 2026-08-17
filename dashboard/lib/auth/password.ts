import crypto from "node:crypto";

// Node's built-in crypto.scrypt -- no bcrypt/argon2 dependency needed
// (avoids native-binding compilation risk). Random 16-byte salt per
// user, stored alongside the hash as "salt:hash" hex.

const SCRYPT_KEY_LENGTH = 64;

export function hashPassword(plainPassword: string): string {
  const salt = crypto.randomBytes(16).toString("hex");
  const derived = crypto.scryptSync(plainPassword, salt, SCRYPT_KEY_LENGTH);
  return `${salt}:${derived.toString("hex")}`;
}

/** Timing-safe comparison -- never a plain `===` on the derived hash. */
export function verifyPassword(plainPassword: string, stored: string): boolean {
  const [salt, hashHex] = stored.split(":");
  if (!salt || !hashHex) return false;
  const expected = Buffer.from(hashHex, "hex");
  const actual = crypto.scryptSync(plainPassword, salt, SCRYPT_KEY_LENGTH);
  if (expected.length !== actual.length) return false;
  return crypto.timingSafeEqual(expected, actual);
}
