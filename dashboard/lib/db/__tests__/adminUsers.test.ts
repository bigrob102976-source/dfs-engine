import { beforeEach, describe, expect, it } from "vitest";

import { countAdminUsers, listAdminUsers } from "../adminUsers";
import { __resetDbForTests } from "../client";
import { insertSubscription } from "../subscriptions";
import { createUser, updateUserRole } from "../users";

beforeEach(() => {
  __resetDbForTests();
});

describe("listAdminUsers / countAdminUsers", () => {
  it("includes users with no subscription at all, with null subscription fields", () => {
    createUser({ email: "bare@example.com", passwordHash: "h" });
    const rows = listAdminUsers();
    expect(rows).toHaveLength(1);
    expect(rows[0].subscription_status).toBeNull();
    expect(rows[0].plan_name).toBeNull();
  });

  it("joins in the user's CURRENT (latest) subscription, not a stale historical one", () => {
    const user = createUser({ email: "switcher@example.com", passwordHash: "h" });
    const first = insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    insertSubscription({ userId: user.id, planId: "monthly", status: "trialing" });

    const rows = listAdminUsers();
    expect(rows[0].plan_id).toBe("monthly");
    expect(rows[0].subscription_status).toBe("trialing");
    expect(rows[0].subscription_id).not.toBe(first.id);
  });

  it("filters by role", () => {
    const admin = createUser({ email: "admin@example.com", passwordHash: "h" });
    updateUserRole(admin.id, "ADMIN");
    createUser({ email: "member@example.com", passwordHash: "h" });

    const admins = listAdminUsers({ role: "ADMIN" });
    expect(admins).toHaveLength(1);
    expect(admins[0].email).toBe("admin@example.com");
  });

  it("filters by search across email and display name", () => {
    createUser({ email: "findme@example.com", passwordHash: "h" });
    createUser({ email: "other@example.com", passwordHash: "h", displayName: "Findme Person" });
    createUser({ email: "nomatch@example.com", passwordHash: "h" });

    expect(listAdminUsers({ search: "findme" })).toHaveLength(2);
  });

  it("filters by subscriptionStatus, including the special 'none' value", () => {
    const active = createUser({ email: "active@example.com", passwordHash: "h" });
    insertSubscription({ userId: active.id, planId: "weekly", status: "active" });
    createUser({ email: "nosub@example.com", passwordHash: "h" });

    expect(listAdminUsers({ subscriptionStatus: "active" })).toHaveLength(1);
    expect(listAdminUsers({ subscriptionStatus: "none" })).toHaveLength(1);
    expect(countAdminUsers({ subscriptionStatus: "none" })).toBe(1);
  });

  it("filters by trialStatus", () => {
    const inTrial = createUser({ email: "intrial@example.com", passwordHash: "h" });
    insertSubscription({ userId: inTrial.id, planId: "weekly", status: "trialing", trialEndsAt: "2099-01-01T00:00:00Z" });
    const expiredTrial = createUser({ email: "expired@example.com", passwordHash: "h" });
    insertSubscription({ userId: expiredTrial.id, planId: "weekly", status: "trialing", trialEndsAt: "2000-01-01T00:00:00Z" });

    expect(listAdminUsers({ trialStatus: "in_trial" })).toHaveLength(2);
    expect(listAdminUsers({ trialStatus: "trial_expired" })).toHaveLength(1);
    expect(listAdminUsers({ trialStatus: "trial_expired" })[0].email).toBe("expired@example.com");
  });
});
