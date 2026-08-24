import { isAdminRole } from "@/lib/auth/roles";
import { listEntitlementsCatalog, listUserEntitlements } from "@/lib/db/entitlements";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";

// A subscription in any of these statuses grants the user every
// entitlement in the catalog -- both launch plans (weekly/monthly)
// provide identical Big Money DFS access today, so this is a single
// status check, not per-plan branching (see CLAUDE.md: never gate
// access with `if plan == monthly`). Adding a second product tier
// later means widening this to consult the plan, not rewriting every
// call site that checks access.
const SUBSCRIPTION_GRANTS_ACCESS_STATUSES = new Set(["trialing", "active", "complimentary"]);

export interface UserAccess {
  isAdmin: boolean;
  entitlementKeys: Set<string>;
}

/** ADMIN gets every entitlement in the catalog unconditionally. A
 * MEMBER's access is the union of: (a) explicit user_entitlements rows
 * (admin-granted complimentary/extra access, never expired), and (b)
 * -- if their most recent subscription is trialing/active/complimentary
 * -- the full entitlement catalog. A canceled/expired/past_due
 * subscription contributes nothing from (b), but explicit grants from
 * (a) still apply. */
export async function computeUserAccess(user: { id: string; role: string }): Promise<UserAccess> {
  if (isAdminRole(user.role)) {
    return { isAdmin: true, entitlementKeys: new Set((await listEntitlementsCatalog()).map((e) => e.key)) };
  }

  const keys = new Set((await listUserEntitlements(user.id)).map((e) => e.entitlement_key));

  const subscription = await getCurrentSubscriptionForUser(user.id);
  if (subscription && SUBSCRIPTION_GRANTS_ACCESS_STATUSES.has(subscription.status)) {
    for (const entitlement of await listEntitlementsCatalog()) keys.add(entitlement.key);
  }

  return { isAdmin: false, entitlementKeys: keys };
}
