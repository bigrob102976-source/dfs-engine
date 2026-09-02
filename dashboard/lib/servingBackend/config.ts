import { isFeatureVisibleToUser } from "../entitlements/featureVisibility";
import { CanonicalPostgresServingBackend } from "./canonicalPostgresBackend";
import { LegacyR2ServingBackend } from "./legacyR2Backend";
import type { ServingBackendKind, SlateServingBackend } from "./types";

// M5C -- the ONE feature-flag key gating canonical Postgres serving.
// Reuses the existing feature_flags/entitlements mechanism (migrations/
// 0012 (SQLite) / migrations-postgres/0013), the same admin toggle
// surface every other optimizer-source flag already uses
// (/api/admin/features/[key]/state), and the same visibility gate
// (isFeatureVisibleToUser) -- no new authorization mechanism invented.
export const CANONICAL_SERVING_FLAG_KEY = "mlb.canonical_postgres_serving";

/** ADMIN_ONLY (the seeded default) -> true only for ADMIN. DISABLED ->
 * false for everyone, even ADMIN (a full kill switch). PRODUCTION/BETA
 * -> true for ADMIN or an entitled MEMBER -- NOT reached until the M5M
 * cutover gate's full proof passes; this function's behavior is correct
 * for that state too, it is simply never set today. */
export async function userCanUseCanonicalServing(user: { id: string; role: string } | null): Promise<boolean> {
  return isFeatureVisibleToUser(user, CANONICAL_SERVING_FLAG_KEY);
}

/** M5C -- the single choke point every customer-facing route must call
 * to pick a serving backend. `requestedKind` is an EXPLICIT, OPT-IN
 * request (e.g. an admin's own UI toggle) -- never inferred from a
 * prior failure, and NEVER honored for a user who doesn't currently
 * pass userCanUseCanonicalServing(). The production default (no
 * requestedKind, or a non-visible user) is ALWAYS LegacyR2ServingBackend
 * -- this function contains the only branch that can ever choose
 * otherwise, so rolling back to legacy for everyone is always exactly
 * "flip the feature flag to DISABLED" (see lib/entitlements/
 * featureVisibility.ts), never a code change. */
export async function resolveServingBackend(
  user: { id: string; role: string } | null, requestedKind?: ServingBackendKind | null,
): Promise<SlateServingBackend> {
  if (requestedKind === "CANONICAL_POSTGRES" && (await userCanUseCanonicalServing(user))) {
    return CanonicalPostgresServingBackend;
  }
  return LegacyR2ServingBackend;
}
