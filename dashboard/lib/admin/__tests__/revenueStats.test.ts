import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { __resetExecutorForTests } from "@/lib/db/executor";
import { cancelSubscription, insertSubscription } from "@/lib/db/subscriptions";
import { createUser } from "@/lib/db/users";

import { computeAdminRevenueStats } from "../revenueStats";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("computeAdminRevenueStats", () => {
  it("returns real zeroes and null/-- placeholders only for genuinely uncalculable metrics on an empty system", async () => {
    const stats = await computeAdminRevenueStats();
    expect(stats.mrrCents).toBe(0);
    expect(stats.arrCents).toBe(0);
    expect(stats.weeklyRevenueCents).toBe(0);
    expect(stats.monthlyRevenueCents).toBe(0);
    expect(stats.newSubscribersThisMonth).toBe(0);
    expect(stats.cancellationsThisMonth).toBe(0);
    expect(stats.trialConversionRatePct).toBeNull();
    expect(stats.churnRatePct).toBeNull();
  });

  it("splits MRR by plan and counts new subscribers this month", async () => {
    const weeklyUser = await createUser({ email: "w@example.com", passwordHash: "h" });
    await insertSubscription({ userId: weeklyUser.id, planId: "weekly", status: "active" });
    const monthlyUser = await createUser({ email: "m@example.com", passwordHash: "h" });
    await insertSubscription({ userId: monthlyUser.id, planId: "monthly", status: "active" });

    const stats = await computeAdminRevenueStats();
    expect(stats.weeklyRevenueCents).toBe(Math.round(1099 * (52 / 12)));
    expect(stats.monthlyRevenueCents).toBe(2999);
    expect(stats.mrrCents).toBe(stats.weeklyRevenueCents + stats.monthlyRevenueCents);
    expect(stats.newSubscribersThisMonth).toBe(2);
  });

  it("counts a cancellation made this month", async () => {
    const user = await createUser({ email: "cancel@example.com", passwordHash: "h" });
    const sub = await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    await cancelSubscription(sub.id);

    const stats = await computeAdminRevenueStats();
    expect(stats.cancellationsThisMonth).toBe(1);
    expect(stats.mrrCents).toBe(0); // no longer active -> no revenue
  });

  it("reports Active/Weekly/Monthly Subscribers, Past Due, and Canceled as real current-status counts", async () => {
    const active = await createUser({ email: "active@example.com", passwordHash: "h" });
    await insertSubscription({ userId: active.id, planId: "weekly", status: "active" });
    const trialing = await createUser({ email: "trialing@example.com", passwordHash: "h" });
    await insertSubscription({ userId: trialing.id, planId: "monthly", status: "trialing" });
    const pastDue = await createUser({ email: "pastdue@example.com", passwordHash: "h" });
    await insertSubscription({ userId: pastDue.id, planId: "weekly", status: "past_due" });
    const canceledUser = await createUser({ email: "canceleduser@example.com", passwordHash: "h" });
    const canceledSub = await insertSubscription({ userId: canceledUser.id, planId: "monthly", status: "active" });
    await cancelSubscription(canceledSub.id);

    const stats = await computeAdminRevenueStats();
    expect(stats.activeSubscribers).toBe(1);
    expect(stats.weeklySubscribers).toBe(1); // active weekly user (trialing/active/complimentary)
    expect(stats.monthlySubscribers).toBe(1); // trialing monthly user
    expect(stats.pastDueSubscribers).toBe(1);
    expect(stats.canceledSubscribers).toBe(1);
  });
});
