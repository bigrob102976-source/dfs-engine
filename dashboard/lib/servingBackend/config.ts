import { isAdminRole } from "../auth/roles";
import { getFeatureFlag } from "../db/featureFlags";
import { CanonicalPostgresServingBackend } from "./canonicalPostgresBackend";
import { LegacyR2ServingBackend } from "./legacyR2Backend";
import type { ServingBackendKind, SlateServingBackend } from "./types";

// M5C -- the ONE feature-flag key gating canonical Postgres serving.
// Reuses the existing feature_flags/entitlements mechanism (migrations/
// 0012 (SQLite) / migrations-postgres/0013), the same admin toggle
// surface every other optimizer-source flag already uses
// (/api/admin/features/[key]/state). The flag STATE machine is the same
// one every other flag uses; only the BETA/PRODUCTION rule differs (no
// per-user entitlement -- see userCanUseCanonicalServing for why), so
// no new authorization mechanism is invented.
export const CANONICAL_SERVING_FLAG_KEY = "mlb.canonical_postgres_serving";

/** DISABLED -> false for everyone, even ADMIN (a full kill switch).
 * ADMIN_ONLY -> true only for ADMIN. BETA/PRODUCTION -> true for ANY
 * authenticated user. The flag has been PRODUCTION since 2026-09-03.
 *
 * This deliberately does NOT go through isFeatureVisibleToUser, which
 * additionally requires a per-user entitlement on BETA/PRODUCTION. That
 * rule is right for gated PRODUCT features (mlb.big_money_ml_optimizer,
 * mlb.bluecollar_optimizer -- both still use it), but wrong here: which
 * backend serves a slate is serving INFRASTRUCTURE, not something a
 * customer buys. Requiring an entitlement meant all 47 members were
 * pinned to LegacyR2ServingBackend -- broken/empty since 2026-09-03 --
 * because the subscriptions table is empty, so "entitled to canonical"
 * had become "entitled to a working site."
 *
 * The admin kill switch is unchanged and still needs no code change:
 * set the flag DISABLED and every user, ADMIN included, falls back to
 * legacy; set it ADMIN_ONLY to re-restrict it to staff.
 *
 * TODO(billing-launch): RESTORE THE ENTITLEMENT GATE. On 2026-09-08 the
 * per-user entitlement check was bypassed here DELIBERATELY, because
 * Big Money DFS is a free beta and the subscriptions table is empty by
 * design -- billing comes later. When paid subscriptions launch, this
 * function must go back to `isFeatureVisibleToUser(user,
 * CANONICAL_SERVING_FLAG_KEY)` (or an equivalent that consults
 * entitlements), or every free account keeps full canonical serving
 * after launch. Recorded in admin_audit_log as
 * "serving_backend.entitlement_gate_bypassed" (see
 * scripts/record-serving-gate-audit.ts). This note exists because the
 * 2026-09-03 flag flip to PRODUCTION went undocumented and cost days of
 * debugging -- do not remove it without doing the restore. */
export async function userCanUseCanonicalServing(user: { id: string; role: string } | null): Promise<boolean> {
  const flag = await getFeatureFlag(CANONICAL_SERVING_FLAG_KEY);
  // An unknown key is never silently allowed -- mirrors isFeatureVisibleToUser.
  if (!flag) return false;
  if (flag.state === "DISABLED") return false;
  if (!user) return false;
  if (flag.state === "ADMIN_ONLY") return isAdminRole(user.role);
  return true;
}

/** M5C -- the single choke point every customer-facing route must call
 * to pick a serving backend. URGENT FIX (2026-09-08): canonical is now
 * the DEFAULT for any user who passes userCanUseCanonicalServing() --
 * previously this required an EXPLICIT `requestedKind === "CANONICAL_
 * POSTGRES"` from the caller, which no customer-facing page ever sent,
 * so flipping the flag to PRODUCTION on 2026-09-03 silently did nothing
 * for real traffic (confirmed live: every ordinary request kept
 * resolving to LegacyR2ServingBackend, which has been broken/empty
 * since the same date).
 *
 * `requestedKind` is still honored in ONE direction only:
 *  - "LEGACY_R2" -> always returns legacy. A deliberate per-request
 *    escape hatch (comparison tooling, and a way to reproduce a legacy
 *    result without touching the flag). Opting DOWN needs no privilege.
 *  - "CANONICAL_POSTGRES" (or undefined) -> falls through to the flag
 *    gate below. An explicit request can never GRANT canonical access
 *    to a user the flag does not already cover.
 *
 * DISABLED remains a full kill switch (userCanUseCanonicalServing
 * returns false for everyone, including ADMIN, when the flag is
 * DISABLED) -- rolling back to legacy for everyone is still always
 * exactly "flip the feature flag to DISABLED," never a code change. */
export async function resolveServingBackend(
  user: { id: string; role: string } | null, requestedKind?: ServingBackendKind | null,
): Promise<SlateServingBackend> {
  if (requestedKind === "LEGACY_R2") {
    return LegacyR2ServingBackend;
  }
  if (await userCanUseCanonicalServing(user)) {
    return CanonicalPostgresServingBackend;
  }
  return LegacyR2ServingBackend;
}
