import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { cancelSubscription, insertSubscription } from "@/lib/db/subscriptions";
import { createUser } from "@/lib/db/users";

import { computeAdminRevenueStats } from "../revenueStats";

beforeEach(() => {
  __resetDbForTests();
});

describe("computeAdminRevenueStats", () => {
  it("returns real zeroes and null/-- placeholders only for genuinely uncalculable metrics on an empty system", () => {
    const stats = computeAdminRevenueStats();
    expect(stats.mrrCents).toBe(0);
    expect(stats.arrCents).toBe(0);
    expect(stats.weeklyRevenueCents).toBe(0);
    expect(stats.monthlyRevenueCents).toBe(0);
    expect(stats.newSubscribersThisMonth).toBe(0);
    expect(stats.cancellationsThisMonth).toBe(0);
    expect(stats.trialConversionRatePct).toBeNull();
    expect(stats.churnRatePct).toBeNull();
  });

  it("splits MRR by plan and counts new subscribers this month", () => {
    const weeklyUser = createUser({ email: "w@example.com", passwordHash: "h" });
    insertSubscription({ userId: weeklyUser.id, planId: "weekly", status: "active" });
    const monthlyUser = createUser({ email: "m@example.com", passwordHash: "h" });
    insertSubscription({ userId: monthlyUser.id, planId: "monthly", status: "active" });

    const stats = computeAdminRevenueStats();
    expect(stats.weeklyRevenueCents).toBe(Math.round(1099 * (52 / 12)));
    expect(stats.monthlyRevenueCents).toBe(2999);
    expect(stats.mrrCents).toBe(stats.weeklyRevenueCents + stats.monthlyRevenueCents);
    expect(stats.newSubscribersThisMonth).toBe(2);
  });

  it("counts a cancellation made this month", () => {
    const user = createUser({ email: "cancel@example.com", passwordHash: "h" });
    const sub = insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    cancelSubscription(sub.id);

    const stats = computeAdminRevenueStats();
    expect(stats.cancellationsThisMonth).toBe(1);
    expect(stats.mrrCents).toBe(0); // no longer active -> no revenue
  });
});
