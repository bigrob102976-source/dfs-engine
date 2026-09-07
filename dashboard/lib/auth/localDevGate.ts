import { isDevelopment } from "@/lib/env";

/** Deliberately dependency-free (only lib/env.ts, itself dependency-free)
 * so this can be imported from the Edge middleware runtime, which cannot
 * load the DB layer (node:sqlite) that lib/auth/localDevAutoLogin.ts
 * pulls in. This is the ONE place the two-part gate is defined --
 * localDevAutoLogin.ts re-exports it rather than redefining it. */
export function isLocalDevAutoLoginEnabled(): boolean {
  return isDevelopment() && process.env.LOCAL_DEV_AUTO_LOGIN === "true";
}
