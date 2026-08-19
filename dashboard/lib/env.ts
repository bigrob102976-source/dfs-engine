// Milestone 30: the ONE place "which environment am I running in" is
// decided. Next.js sets NODE_ENV automatically (development for `next
// dev`, production for `next build && next start`, test for vitest --
// see vitest.config.ts) -- this module never re-derives that from
// anything else (a hostname, a hardcoded flag, etc.), so it can never
// drift from what the runtime actually is.

export type AppEnvironment = "development" | "test" | "production";

export function getAppEnvironment(): AppEnvironment {
  const raw = process.env.NODE_ENV;
  if (raw === "production") return "production";
  if (raw === "test") return "test";
  return "development";
}

export function isProduction(): boolean {
  return getAppEnvironment() === "production";
}

export function isDevelopment(): boolean {
  return getAppEnvironment() === "development";
}

export function isTest(): boolean {
  return getAppEnvironment() === "test";
}

/** Milestone 30: PRIVATE_BETA=true restricts member-product access to
 * ADMIN + explicitly beta-approved users (see lib/auth/betaAccess.ts).
 * Off by default -- never silently restrictive, matching every other
 * explicit-opt-in flag in this project (Mock Mode, etc.). */
export function isPrivateBetaEnabled(): boolean {
  return process.env.PRIVATE_BETA === "true";
}
