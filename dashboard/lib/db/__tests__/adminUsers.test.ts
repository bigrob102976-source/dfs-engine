import { beforeEach, describe, expect, it } from "vitest";

import { countAdminUsers, listAdminUsers } from "../adminUsers";
import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
import { insertSubscription } from "../subscriptions";
import { createUser, updateUserRole } from "../users";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("listAdminUsers / countAdminUsers", () => {
  it("includes users with no subscription at all, with null subscription fields", async () => {
    await createUser({ email: "bare@example.com", passwordHash: "h" });
    const rows = await listAdminUsers();
    expect(rows).toHaveLength(1);
    expect(rows[0].subscription_status).toBeNull();
    expect(rows[0].plan_name).toBeNull();
  });

  it("joins in the user's CURRENT (latest) subscription, not a stale historical one", async () => {
    const user = await createUser({ email: "switcher@example.com", passwordHash: "h" });
    const first = await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
    await insertSubscription({ userId: user.id, planId: "monthly", status: "trialing" });

    const rows = await listAdminUsers();
    expect(rows[0].plan_id).toBe("monthly");
    expect(rows[0].subscription_status).toBe("trialing");
    expect(rows[0].subscription_id).not.toBe(first.id);
  });

  it("filters by role", async () => {
    const admin = await createUser({ email: "admin@example.com", passwordHash: "h" });
    await updateUserRole(admin.id, "ADMIN");
    await createUser({ email: "member@example.com", passwordHash: "h" });

    const admins = await listAdminUsers({ role: "ADMIN" });
    expect(admins).toHaveLength(1);
    expect(admins[0].email).toBe("admin@example.com");
  });

  it("filters by search across email and display name", async () => {
    await createUser({ email: "findme@example.com", passwordHash: "h" });
    await createUser({ email: "other@example.com", passwordHash: "h", displayName: "Findme Person" });
    await createUser({ email: "nomatch@example.com", passwordHash: "h" });

    expect(await listAdminUsers({ search: "findme" })).toHaveLength(2);
  });

  it("filters by subscriptionStatus, including the special 'none' value", async () => {
    const active = await createUser({ email: "active@example.com", passwordHash: "h" });
    await insertSubscription({ userId: active.id, planId: "weekly", status: "active" });
    await createUser({ email: "nosub@example.com", passwordHash: "h" });

    expect(await listAdminUsers({ subscriptionStatus: "active" })).toHaveLength(1);
    expect(await listAdminUsers({ subscriptionStatus: "none" })).toHaveLength(1);
    expect(await countAdminUsers({ subscriptionStatus: "none" })).toBe(1);
  });

  it("filters by trialStatus", async () => {
    const inTrial = await createUser({ email: "intrial@example.com", passwordHash: "h" });
    await insertSubscription({ userId: inTrial.id, planId: "weekly", status: "trialing", trialEndsAt: "2099-01-01T00:00:00Z" });
    const expiredTrial = await createUser({ email: "expired@example.com", passwordHash: "h" });
    await insertSubscription({ userId: expiredTrial.id, planId: "weekly", status: "trialing", trialEndsAt: "2000-01-01T00:00:00Z" });

    expect(await listAdminUsers({ trialStatus: "in_trial" })).toHaveLength(2);
    expect(await listAdminUsers({ trialStatus: "trial_expired" })).toHaveLength(1);
    expect((await listAdminUsers({ trialStatus: "trial_expired" }))[0].email).toBe("expired@example.com");
  });
});
