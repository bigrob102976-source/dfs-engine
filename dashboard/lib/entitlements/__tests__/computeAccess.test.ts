import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { grantUserEntitlement } from "@/lib/db/entitlements";
import { insertSubscription } from "@/lib/db/subscriptions";
import type { SubscriptionStatus } from "@/lib/db/types";
import { createUser, findUserById, updateUserRole } from "@/lib/db/users";

import { computeUserAccess } from "../computeAccess";

beforeEach(() => {
  __resetDbForTests();
});

describe("computeUserAccess", () => {
  it("ADMIN gets every entitlement in the catalog with no subscription at all", () => {
    const created = createUser({ email: "admin@example.com", passwordHash: "h" });
    updateUserRole(created.id, "ADMIN");
    // updateUserRole mutates the DB row, not the `created` object in
    // hand -- re-fetch so computeUserAccess sees the real current role,
    // same discipline every guard/session lookup in this milestone uses.
    const user = findUserById(created.id)!;
    const access = computeUserAccess(user);
    expect(access.isAdmin).toBe(true);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
    expect(access.entitlementKeys.has("mlb.ai_projections")).toBe(true);
    expect(access.entitlementKeys.size).toBeGreaterThan(0);
  });

  it("MEMBER with no subscription and no explicit grants gets nothing", () => {
    const user = createUser({ email: "bare@example.com", passwordHash: "h" });
    const access = computeUserAccess(user);
    expect(access.isAdmin).toBe(false);
    expect(access.entitlementKeys.size).toBe(0);
  });

  it.each<[SubscriptionStatus, boolean]>([
    ["trialing", true],
    ["active", true],
    ["complimentary", true],
    ["past_due", false],
    ["canceled", false],
    ["expired", false],
  ])("subscription status '%s' grants full catalog access = %s", (status, expectFullAccess) => {
    const user = createUser({ email: `${status}@example.com`, passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "weekly", status });
    const access = computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(expectFullAccess);
  });

  it("an explicit grant is honored even without any subscription", () => {
    const user = createUser({ email: "granted@example.com", passwordHash: "h" });
    grantUserEntitlement({ userId: user.id, entitlementKey: "mlb.optimizer", grantedBy: null, reason: "test grant" });
    const access = computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
    expect(access.entitlementKeys.has("mlb.research")).toBe(false);
  });

  it("an explicit grant still applies even when the subscription is canceled", () => {
    const user = createUser({ email: "mixed@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
    grantUserEntitlement({ userId: user.id, entitlementKey: "mlb.optimizer", grantedBy: null });
    const access = computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
    expect(access.entitlementKeys.has("mlb.research")).toBe(false);
  });

  it("an expired explicit grant is not honored", () => {
    const user = createUser({ email: "expiredgrant@example.com", passwordHash: "h" });
    grantUserEntitlement({
      userId: user.id,
      entitlementKey: "mlb.optimizer",
      grantedBy: null,
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    });
    const access = computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(false);
  });

  it("only the most recent subscription row matters", () => {
    const user = createUser({ email: "history@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
    insertSubscription({ userId: user.id, planId: "monthly", status: "active" });
    const access = computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
  });
});
