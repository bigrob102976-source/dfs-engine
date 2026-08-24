import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
import {
  cancelSubscription,
  countCurrentSubscribersByPlan,
  countSubscriptionsByStatus,
  findSubscriptionByProviderSubscriptionId,
  getCurrentSubscriptionForUser,
  getSubscriptionById,
  insertSubscription,
  listSubscriptions,
  updateSubscriptionStatus,
} from "../subscriptions";
import { createUser, setStripeCustomerId } from "../users";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("countSubscriptionsByStatus", () => {
  it("counts each user once by their current status, not once per historical row", async () => {
    // A user who canceled a weekly plan, then started a NEW monthly
    // trial -- this produces two rows for the same user (an old
    // canceled one kept for history, and a new trialing one).
    const user = await createUser({ email: "churned@example.com", passwordHash: "h" });
    const first = await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    await cancelSubscription(first.id);
    await insertSubscription({ userId: user.id, planId: "monthly", status: "trialing" });

    const counts = await countSubscriptionsByStatus();
    expect(counts.trialing).toBe(1);
    expect(counts.canceled).toBe(0); // NOT counted -- superseded by the newer row
  });

  it("counts multiple distinct users independently", async () => {
    const a = await createUser({ email: "a@example.com", passwordHash: "h" });
    const b = await createUser({ email: "b@example.com", passwordHash: "h" });
    await insertSubscription({ userId: a.id, planId: "weekly", status: "active" });
    await insertSubscription({ userId: b.id, planId: "monthly", status: "trialing" });

    const counts = await countSubscriptionsByStatus();
    expect(counts.active).toBe(1);
    expect(counts.trialing).toBe(1);
  });

  it("returns all-zero counts with no subscriptions at all", async () => {
    expect(await countSubscriptionsByStatus()).toEqual({
      trialing: 0, active: 0, past_due: 0, canceled: 0, expired: 0, complimentary: 0,
    });
  });
});

describe("countCurrentSubscribersByPlan", () => {
  it("counts only currently-access-granting statuses for that plan", async () => {
    const active = await createUser({ email: "active@example.com", passwordHash: "h" });
    const canceled = await createUser({ email: "canceled@example.com", passwordHash: "h" });
    await insertSubscription({ userId: active.id, planId: "weekly", status: "active" });
    await insertSubscription({ userId: canceled.id, planId: "weekly", status: "canceled" });

    expect(await countCurrentSubscribersByPlan("weekly")).toBe(1);
    expect(await countCurrentSubscribersByPlan("monthly")).toBe(0);
  });

  it("does not count a user's superseded plan after they switch plans", async () => {
    const user = await createUser({ email: "switcher@example.com", passwordHash: "h" });
    const first = await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    await cancelSubscription(first.id);
    await insertSubscription({ userId: user.id, planId: "monthly", status: "active" });

    expect(await countCurrentSubscribersByPlan("weekly")).toBe(0);
    expect(await countCurrentSubscribersByPlan("monthly")).toBe(1);
  });
});

describe("getCurrentSubscriptionForUser (rowid tiebreak sanity)", () => {
  it("returns the most recently inserted row even with identical timestamps", async () => {
    const user = await createUser({ email: "tiebreak@example.com", passwordHash: "h" });
    await insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
    const second = await insertSubscription({ userId: user.id, planId: "monthly", status: "active" });
    expect((await getCurrentSubscriptionForUser(user.id))?.id).toBe(second.id);
  });
});

describe("insertSubscription (Stripe fields)", () => {
  it("defaults to provider='dev' with null Stripe fields and cancel_at_period_end=0 when omitted", async () => {
    const user = await createUser({ email: "devdefault@example.com", passwordHash: "h" });
    const sub = await insertSubscription({ userId: user.id, planId: "weekly", status: "trialing" });
    expect(sub.provider).toBe("dev");
    expect(sub.provider_subscription_id).toBeNull();
    expect(sub.provider_price_id).toBeNull();
    expect(sub.current_period_start).toBeNull();
    expect(sub.cancel_at_period_end).toBe(0);
    expect(sub.last_stripe_event_at).toBeNull();
  });

  it("persists every Stripe field when provided", async () => {
    const user = await createUser({ email: "stripefields@example.com", passwordHash: "h" });
    const sub = await insertSubscription({
      userId: user.id,
      planId: "monthly",
      status: "trialing",
      provider: "stripe",
      providerSubscriptionId: "sub_abc123",
      providerPriceId: "price_xyz789",
      trialEndsAt: "2026-09-01T00:00:00Z",
      currentPeriodStart: "2026-08-29T00:00:00Z",
      currentPeriodEnd: "2026-09-29T00:00:00Z",
      cancelAtPeriodEnd: true,
      lastStripeEventAt: "2026-08-29T00:00:05Z",
    });
    expect(sub.provider).toBe("stripe");
    expect(sub.provider_subscription_id).toBe("sub_abc123");
    expect(sub.provider_price_id).toBe("price_xyz789");
    expect(sub.current_period_start).toBe("2026-08-29T00:00:00Z");
    expect(sub.cancel_at_period_end).toBe(1);
    expect(sub.last_stripe_event_at).toBe("2026-08-29T00:00:05Z");
  });
});

describe("findSubscriptionByProviderSubscriptionId", () => {
  it("finds a subscription by its Stripe subscription ID", async () => {
    const user = await createUser({ email: "findbyprov@example.com", passwordHash: "h" });
    const sub = await insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "active",
      provider: "stripe",
      providerSubscriptionId: "sub_findme",
    });
    expect((await findSubscriptionByProviderSubscriptionId("sub_findme"))?.id).toBe(sub.id);
  });

  it("returns null when no subscription has that provider_subscription_id", async () => {
    expect(await findSubscriptionByProviderSubscriptionId("sub_does_not_exist")).toBeNull();
  });
});

describe("updateSubscriptionStatus (widened patch fields)", () => {
  it("updates current_period_start, cancel_at_period_end, provider_price_id, and last_stripe_event_at", async () => {
    const user = await createUser({ email: "widenedpatch@example.com", passwordHash: "h" });
    const sub = await insertSubscription({ userId: user.id, planId: "weekly", status: "trialing", provider: "stripe" });

    await updateSubscriptionStatus(sub.id, "active", {
      current_period_start: "2026-08-01T00:00:00Z",
      current_period_end: "2026-08-08T00:00:00Z",
      cancel_at_period_end: 1,
      provider_price_id: "price_weekly_test",
      last_stripe_event_at: "2026-08-01T00:00:01Z",
    });

    const updated = (await getSubscriptionById(sub.id))!;
    expect(updated.status).toBe("active");
    expect(updated.current_period_start).toBe("2026-08-01T00:00:00Z");
    expect(updated.cancel_at_period_end).toBe(1);
    expect(updated.provider_price_id).toBe("price_weekly_test");
    expect(updated.last_stripe_event_at).toBe("2026-08-01T00:00:01Z");
  });

  it("correctly applies cancel_at_period_end=0 (not treated as 'omitted' by COALESCE)", async () => {
    const user = await createUser({ email: "zerofalsy@example.com", passwordHash: "h" });
    const sub = await insertSubscription({ userId: user.id, planId: "weekly", status: "active", cancelAtPeriodEnd: true });
    expect((await getSubscriptionById(sub.id))!.cancel_at_period_end).toBe(1);

    await updateSubscriptionStatus(sub.id, "active", { cancel_at_period_end: 0 });
    expect((await getSubscriptionById(sub.id))!.cancel_at_period_end).toBe(0);
  });

  it("leaves unspecified fields untouched", async () => {
    const user = await createUser({ email: "untouched@example.com", passwordHash: "h" });
    const sub = await insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "trialing",
      providerPriceId: "price_original",
    });
    await updateSubscriptionStatus(sub.id, "active", {});
    expect((await getSubscriptionById(sub.id))!.provider_price_id).toBe("price_original");
  });
});

describe("listSubscriptions (Stripe customer id join)", () => {
  it("includes the user's stripe_customer_id in the admin listing", async () => {
    const user = await createUser({ email: "listjoin@example.com", passwordHash: "h" });
    await setStripeCustomerId(user.id, "cus_listjoin");
    await insertSubscription({ userId: user.id, planId: "weekly", status: "active", provider: "stripe" });

    const rows = await listSubscriptions({ search: "listjoin" });
    expect(rows).toHaveLength(1);
    expect(rows[0].user_stripe_customer_id).toBe("cus_listjoin");
  });
});
