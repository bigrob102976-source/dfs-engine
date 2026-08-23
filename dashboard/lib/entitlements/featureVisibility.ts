import { isAdminRole } from "@/lib/auth/roles";
import { getFeatureFlag, listFeatureFlags } from "@/lib/db/featureFlags";

import { userHasEntitlement } from "./hasEntitlement";

/** Two independent gates must both pass for a feature to be usable:
 * (1) the admin-controlled feature_flags.state for that key, and
 * (2) the requesting user's own entitlement (unless they're ADMIN).
 *
 *   DISABLED    -> hidden from EVERYONE, including ADMIN (a true kill switch).
 *   ADMIN_ONLY  -> visible only to ADMIN, regardless of entitlement.
 *   BETA / PRODUCTION -> visible to ADMIN always, or to a MEMBER who
 *                        holds the matching entitlement.
 *
 * An unknown feature key (no feature_flags row at all) is never
 * silently allowed -- it's treated as not visible. */
export function isFeatureVisibleToUser(user: { id: string; role: string } | null, key: string): boolean {
  const flag = getFeatureFlag(key);
  if (!flag) return false;
  if (flag.state === "DISABLED") return false;
  if (!user) return false;

  const admin = isAdminRole(user.role);
  if (flag.state === "ADMIN_ONLY") return admin;
  return admin || userHasEntitlement(user, key);
}

export function listVisibleFeatureKeysForUser(user: { id: string; role: string } | null): Set<string> {
  const keys = new Set<string>();
  for (const flag of listFeatureFlags()) {
    if (isFeatureVisibleToUser(user, flag.key)) keys.add(flag.key);
  }
  return keys;
}

export const BIG_MONEY_ML_OPTIMIZER_FLAG_KEY = "mlb.big_money_ml_optimizer";

/** Milestone 32.4: server-side gate for selecting Big Money ML as an
 * optimizer projection source -- checked in BOTH the build and validate
 * API routes (never trust the UI selector alone). Reuses the same
 * feature-flag/entitlement machinery every other gated capability in
 * this app already goes through; no new authorization mechanism. */
export function userCanSelectBigMoneyMlOptimizerSource(user: { id: string; role: string } | null): boolean {
  return isFeatureVisibleToUser(user, BIG_MONEY_ML_OPTIMIZER_FLAG_KEY);
}
