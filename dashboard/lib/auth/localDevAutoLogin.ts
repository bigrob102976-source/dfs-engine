import crypto from "node:crypto";

import { hashPassword } from "@/lib/auth/password";
import { establishSession, getCurrentUser } from "@/lib/auth/session";
import { createUser, findUserByEmail, setEmailVerified, updateUserRole } from "@/lib/db/users";
import { isLocalDevAutoLoginEnabled } from "@/lib/auth/localDevGate";

// Re-exported (not redefined) so there's exactly one place the two-part
// gate is evaluated. Lives in its own dependency-free module because
// middleware.ts -- which must run in the Edge runtime -- needs the gate
// but can't load this file's DB imports (node:sqlite).
export { isLocalDevAutoLoginEnabled };

const DEFAULT_LOCAL_DEV_ADMIN_EMAIL = "bigrob102976@gmail.com";

/** Local-development-only session bootstrap. Reuses the REAL session
 * system end to end -- establishSession() is the exact same function
 * every real login calls, so requireAdmin()/requireAuth() are never
 * touched, weakened, or special-cased; they just find a genuine
 * session already in place. No-ops (idempotent) if a real session
 * already exists, so this never re-issues a session on every request.
 *
 * The bootstrapped account's password is a 32-byte random value
 * generated fresh, hashed with the project's real hashPassword(), and
 * then discarded -- it is never logged, returned, or stored anywhere
 * but its one-way hash. That means this specific account can NEVER be
 * signed into through the normal /login form by anyone, including this
 * code after this function returns; the only way to obtain a session
 * for it is this exact dev-gated bootstrap path. */
export async function maybeAutoLoginLocalDev(): Promise<void> {
  if (!isLocalDevAutoLoginEnabled()) return;

  const existing = await getCurrentUser();
  if (existing) return;

  const email = (process.env.LOCAL_DEV_ADMIN_EMAIL || DEFAULT_LOCAL_DEV_ADMIN_EMAIL).toLowerCase();
  let user = await findUserByEmail(email);

  if (!user) {
    const randomPassword = crypto.randomBytes(32).toString("hex");
    user = await createUser({ email, passwordHash: hashPassword(randomPassword), displayName: "Local Dev Admin" });
    await setEmailVerified(user.id);
  }

  if (user.role !== "ADMIN") {
    await updateUserRole(user.id, "ADMIN");
  }

  await establishSession(user.id, "local-dev-auto-login");
}
