import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { __resetExecutorForTests } from "@/lib/db/executor";
import { insertSubscription, updateSubscriptionStatus } from "@/lib/db/subscriptions";
import { createUser } from "@/lib/db/users";

import { computeAdminOverviewStats } from "../overviewStats";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("computeAdminOverviewStats", () => {
  it("returns all-zero real figures (not fabricated placeholders) with no users at all", async () => {
    const stats = await computeAdminOverviewStats();
    expect(stats.totalUsers).toBe(0);
    expect(stats.activeMembers).toBe(0);
    expect(stats.mrrCents).toBe(0);
    expect(stats.arrCents).toBe(0);
    expect(stats.trialConversionRatePct).toBeNull(); // no one has ever trialed -- genuinely uncalculable
  });

  it("computes MRR from actual active-subscriber counts times seeded plan prices", async () => {
    const weeklyUser = await createUser({ email: "weekly@example.com", passwordHash: "h" });
    await insertSubscription({ userId: weeklyUser.id, planId: "weekly", status: "active" });
    const monthlyUser = await createUser({ email: "monthly@example.com", passwordHash: "h" });
    await insertSubscription({ userId: monthlyUser.id, planId: "monthly", status: "active" });

    const stats = await computeAdminOverviewStats();
    // weekly $10.99 * (52/12) + monthly $29.99, in cents, rounded.
    const expectedMrr = Math.round(1099 * (52 / 12) + 2999);
    expect(stats.mrrCents).toBe(expectedMrr);
    expect(stats.arrCents).toBe(expectedMrr * 12);
    expect(stats.weeklyMembers).toBe(1);
    expect(stats.monthlyMembers).toBe(1);
  });

  it("does not count trialing or complimentary subscribers toward MRR", async () => {
    const trialUser = await createUser({ email: "trial@example.com", passwordHash: "h" });
    await insertSubscription({ userId: trialUser.id, planId: "weekly", status: "trialing" });
    const compUser = await createUser({ email: "comp@example.com", passwordHash: "h" });
    await insertSubscription({ userId: compUser.id, planId: "monthly", status: "complimentary" });

    const stats = await computeAdminOverviewStats();
    expect(stats.mrrCents).toBe(0);
    expect(stats.activeTrials).toBe(1);
    expect(stats.complimentaryAccounts).toBe(1);
    // Both still count as "current members" of their plan even though non-revenue.
    expect(stats.weeklyMembers).toBe(1);
    expect(stats.monthlyMembers).toBe(1);
  });

  it("computes trial conversion rate from trial-ever vs currently-active", async () => {
    // A real trial->active conversion mutates the SAME subscription row's
    // status in place (no new row is inserted) -- trial_ends_at is what
    // survives as the "this had a trial" signal, not status='trialing'.
    const converted = await createUser({ email: "converted@example.com", passwordHash: "h" });
    const sub = await insertSubscription({
      userId: converted.id,
      planId: "weekly",
      status: "trialing",
      trialEndsAt: "2026-08-01T00:00:00Z",
    });
    await updateSubscriptionStatus(sub.id, "active");

    const stillTrialing = await createUser({ email: "stilltrial@example.com", passwordHash: "h" });
    await insertSubscription({
      userId: stillTrialing.id,
      planId: "monthly",
      status: "trialing",
      trialEndsAt: "2026-08-30T00:00:00Z",
    });

    const stats = await computeAdminOverviewStats();
    // 1 of 2 users who ever trialed is currently active -> 50%.
    expect(stats.trialConversionRatePct).toBeCloseTo(50, 5);
  });
});
