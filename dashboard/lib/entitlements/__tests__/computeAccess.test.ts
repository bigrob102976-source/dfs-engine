import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { __resetExecutorForTests } from "@/lib/db/executor";
import { grantUserEntitlement } from "@/lib/db/entitlements";
import { insertSubscription } from "@/lib/db/subscriptions";
import type { SubscriptionStatus } from "@/lib/db/types";
import { createUser, findUserById, updateUserRole } from "@/lib/db/users";

import { computeUserAccess } from "../computeAccess";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("computeUserAccess", () => {
  it("ADMIN gets every entitlement in the catalog with no subscription at all", async () => {
    const created = await createUser({ email: "admin@example.com", passwordHash: "h" });
    await updateUserRole(created.id, "ADMIN");
    // updateUserRole mutates the DB row, not the `created` object in
    // hand -- re-fetch so computeUserAccess sees the real current role,
    // same discipline every guard/session lookup in this milestone uses.
    const user = (await findUserById(created.id))!;
    const access = await computeUserAccess(user);
    expect(access.isAdmin).toBe(true);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
    expect(access.entitlementKeys.has("mlb.ai_projections")).toBe(true);
    expect(access.entitlementKeys.size).toBeGreaterThan(0);
  });

  it("MEMBER with no subscription and no explicit grants gets nothing", async () => {
    const user = await createUser({ email: "bare@example.com", passwordHash: "h" });
    const access = await computeUserAccess(user);
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
  ])("subscription status '%s' grants full catalog access = %s", async (status, expectFullAccess) => {
    const user = await createUser({ email: `${status}@example.com`, passwordHash: "h" });
    await insertSubscription({ userId: user.id, planId: "weekly", status });
    const access = await computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(expectFullAccess);
  });

  it("an explicit grant is honored even without any subscription", async () => {
    const user = await createUser({ email: "granted@example.com", passwordHash: "h" });
    await grantUserEntitlement({ userId: user.id, entitlementKey: "mlb.optimizer", grantedBy: null, reason: "test grant" });
    const access = await computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
    expect(access.entitlementKeys.has("mlb.research")).toBe(false);
  });

  it("an explicit grant still applies even when the subscription is canceled", async () => {
    const user = await createUser({ email: "mixed@example.com", passwordHash: "h" });
    await insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
    await grantUserEntitlement({ userId: user.id, entitlementKey: "mlb.optimizer", grantedBy: null });
    const access = await computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
    expect(access.entitlementKeys.has("mlb.research")).toBe(false);
  });

  it("an expired explicit grant is not honored", async () => {
    const user = await createUser({ email: "expiredgrant@example.com", passwordHash: "h" });
    await grantUserEntitlement({
      userId: user.id,
      entitlementKey: "mlb.optimizer",
      grantedBy: null,
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    });
    const access = await computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(false);
  });

  it("only the most recent subscription row matters", async () => {
    const user = await createUser({ email: "history@example.com", passwordHash: "h" });
    await insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
    await insertSubscription({ userId: user.id, planId: "monthly", status: "active" });
    const access = await computeUserAccess(user);
    expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
  });

  // Milestone 22: computeUserAccess() was written before Stripe existed
  // and only ever reads `status` -- never `provider` -- so a real
  // Stripe-backed subscription should grant IDENTICAL access to an
  // otherwise-equivalent dev-provider one, with zero code changes to
  // this file. These tests prove that parity explicitly rather than
  // just asserting it in a comment.
  describe("Stripe-provider subscriptions grant identical access to dev-provider ones (no code change needed here)", () => {
    it.each<[SubscriptionStatus, boolean]>([
      ["trialing", true],
      ["active", true],
      ["complimentary", true],
      ["past_due", false],
      ["canceled", false],
      ["expired", false],
    ])("a real Stripe-provider subscription with status '%s' grants full catalog access = %s", async (status, expectFullAccess) => {
      const user = await createUser({ email: `stripe-${status}@example.com`, passwordHash: "h" });
      await insertSubscription({
        userId: user.id,
        planId: "monthly",
        status,
        provider: "stripe",
        providerSubscriptionId: `sub_${status}`,
        providerPriceId: "price_monthly_test",
        currentPeriodStart: "2026-08-01T00:00:00Z",
        currentPeriodEnd: "2026-09-01T00:00:00Z",
        cancelAtPeriodEnd: false,
      });
      const access = await computeUserAccess(user);
      expect(access.entitlementKeys.has("mlb.optimizer")).toBe(expectFullAccess);
    });

    it("a Stripe subscription with cancel_at_period_end=true still grants access until Stripe actually ends it (status stays active)", async () => {
      const user = await createUser({ email: "stripe-cancelatperiodend@example.com", passwordHash: "h" });
      await insertSubscription({
        userId: user.id,
        planId: "weekly",
        status: "active",
        provider: "stripe",
        providerSubscriptionId: "sub_cancelatperiodend",
        cancelAtPeriodEnd: true,
      });
      const access = await computeUserAccess(user);
      expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
    });

    it("an explicit entitlement grant still applies independently of a Stripe subscription's status", async () => {
      const user = await createUser({ email: "stripe-explicitgrant@example.com", passwordHash: "h" });
      await insertSubscription({ userId: user.id, planId: "weekly", status: "canceled", provider: "stripe", providerSubscriptionId: "sub_explicit" });
      await grantUserEntitlement({ userId: user.id, entitlementKey: "mlb.optimizer", grantedBy: null });
      const access = await computeUserAccess(user);
      expect(access.entitlementKeys.has("mlb.optimizer")).toBe(true);
      expect(access.entitlementKeys.has("mlb.research")).toBe(false);
    });
  });
});
