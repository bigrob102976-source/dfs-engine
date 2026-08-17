import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import {
  cancelSubscription,
  countCurrentSubscribersByPlan,
  countSubscriptionsByStatus,
  getCurrentSubscriptionForUser,
  insertSubscription,
} from "../subscriptions";
import { createUser } from "../users";

beforeEach(() => {
  __resetDbForTests();
});

describe("countSubscriptionsByStatus", () => {
  it("counts each user once by their current status, not once per historical row", () => {
    // A user who canceled a weekly plan, then started a NEW monthly
    // trial -- this produces two rows for the same user (an old
    // canceled one kept for history, and a new trialing one).
    const user = createUser({ email: "churned@example.com", passwordHash: "h" });
    const first = insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    cancelSubscription(first.id);
    insertSubscription({ userId: user.id, planId: "monthly", status: "trialing" });

    const counts = countSubscriptionsByStatus();
    expect(counts.trialing).toBe(1);
    expect(counts.canceled).toBe(0); // NOT counted -- superseded by the newer row
  });

  it("counts multiple distinct users independently", () => {
    const a = createUser({ email: "a@example.com", passwordHash: "h" });
    const b = createUser({ email: "b@example.com", passwordHash: "h" });
    insertSubscription({ userId: a.id, planId: "weekly", status: "active" });
    insertSubscription({ userId: b.id, planId: "monthly", status: "trialing" });

    const counts = countSubscriptionsByStatus();
    expect(counts.active).toBe(1);
    expect(counts.trialing).toBe(1);
  });

  it("returns all-zero counts with no subscriptions at all", () => {
    expect(countSubscriptionsByStatus()).toEqual({
      trialing: 0, active: 0, past_due: 0, canceled: 0, expired: 0, complimentary: 0,
    });
  });
});

describe("countCurrentSubscribersByPlan", () => {
  it("counts only currently-access-granting statuses for that plan", () => {
    const active = createUser({ email: "active@example.com", passwordHash: "h" });
    const canceled = createUser({ email: "canceled@example.com", passwordHash: "h" });
    insertSubscription({ userId: active.id, planId: "weekly", status: "active" });
    insertSubscription({ userId: canceled.id, planId: "weekly", status: "canceled" });

    expect(countCurrentSubscribersByPlan("weekly")).toBe(1);
    expect(countCurrentSubscribersByPlan("monthly")).toBe(0);
  });

  it("does not count a user's superseded plan after they switch plans", () => {
    const user = createUser({ email: "switcher@example.com", passwordHash: "h" });
    const first = insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    cancelSubscription(first.id);
    insertSubscription({ userId: user.id, planId: "monthly", status: "active" });

    expect(countCurrentSubscribersByPlan("weekly")).toBe(0);
    expect(countCurrentSubscribersByPlan("monthly")).toBe(1);
  });
});

describe("getCurrentSubscriptionForUser (rowid tiebreak sanity)", () => {
  it("returns the most recently inserted row even with identical timestamps", () => {
    const user = createUser({ email: "tiebreak@example.com", passwordHash: "h" });
    insertSubscription({ userId: user.id, planId: "weekly", status: "canceled" });
    const second = insertSubscription({ userId: user.id, planId: "monthly", status: "active" });
    expect(getCurrentSubscriptionForUser(user.id)?.id).toBe(second.id);
  });
});
