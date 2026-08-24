import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { __resetExecutorForTests } from "../executor";
import {
  countAdmins,
  countUsers,
  createUser,
  findUserByEmail,
  findUserById,
  findUserByStripeCustomerId,
  listUsers,
  markTrialConsumed,
  setBetaAccess,
  setStripeCustomerId,
  setUserDisabled,
  updateUserRole,
} from "../users";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

describe("users", () => {
  it("creates a user with default role MEMBER", async () => {
    const user = await createUser({ email: "test@example.com", passwordHash: "hash" });
    expect(user.role).toBe("MEMBER");
    expect(user.email).toBe("test@example.com");
    expect(user.email_verified_at).toBeNull();
  });

  it("finds a user by email case-insensitively", async () => {
    await createUser({ email: "Test@Example.com", passwordHash: "hash" });
    expect(await findUserByEmail("test@example.com")).not.toBeNull();
    expect(await findUserByEmail("TEST@EXAMPLE.COM")).not.toBeNull();
  });

  it("returns null for an unknown email or id", async () => {
    expect(await findUserByEmail("nobody@example.com")).toBeNull();
    expect(await findUserById("no-such-id")).toBeNull();
  });

  it("rejects a duplicate email", async () => {
    await createUser({ email: "dupe@example.com", passwordHash: "hash" });
    await expect(createUser({ email: "dupe@example.com", passwordHash: "hash2" })).rejects.toThrow();
  });

  it("updateUserRole persists the new role", async () => {
    const user = await createUser({ email: "promote@example.com", passwordHash: "hash" });
    await updateUserRole(user.id, "ADMIN");
    expect((await findUserById(user.id))!.role).toBe("ADMIN");
  });

  it("countAdmins reflects role changes", async () => {
    expect(await countAdmins()).toBe(0);
    const user = await createUser({ email: "admin@example.com", passwordHash: "hash" });
    await updateUserRole(user.id, "ADMIN");
    expect(await countAdmins()).toBe(1);
  });

  it("setUserDisabled sets and clears disabled_at", async () => {
    const user = await createUser({ email: "disable@example.com", passwordHash: "hash" });
    await setUserDisabled(user.id, true);
    expect((await findUserById(user.id))!.disabled_at).not.toBeNull();
    await setUserDisabled(user.id, false);
    expect((await findUserById(user.id))!.disabled_at).toBeNull();
  });

  it("listUsers filters by search and role", async () => {
    const a = await createUser({ email: "alpha@example.com", passwordHash: "h", displayName: "Alpha" });
    await createUser({ email: "beta@example.com", passwordHash: "h", displayName: "Beta" });
    await updateUserRole(a.id, "ADMIN");

    expect((await listUsers({ search: "alpha" })).map((u) => u.email)).toEqual(["alpha@example.com"]);
    expect((await listUsers({ role: "ADMIN" })).map((u) => u.email)).toEqual(["alpha@example.com"]);
    expect((await listUsers({})).length).toBe(2);
  });

  it("countUsers matches listUsers filtering", async () => {
    await createUser({ email: "one@example.com", passwordHash: "h" });
    await createUser({ email: "two@example.com", passwordHash: "h" });
    expect(await countUsers({})).toBe(2);
    expect(await countUsers({ search: "one" })).toBe(1);
  });

  it("a new user has null stripe_customer_id and trial_consumed_at", async () => {
    const user = await createUser({ email: "fresh@example.com", passwordHash: "h" });
    expect(user.stripe_customer_id).toBeNull();
    expect(user.trial_consumed_at).toBeNull();
  });

  it("setStripeCustomerId / findUserByStripeCustomerId round-trip", async () => {
    const user = await createUser({ email: "cus@example.com", passwordHash: "h" });
    await setStripeCustomerId(user.id, "cus_abc123");
    expect((await findUserById(user.id))!.stripe_customer_id).toBe("cus_abc123");
    expect((await findUserByStripeCustomerId("cus_abc123"))?.id).toBe(user.id);
  });

  it("findUserByStripeCustomerId returns null for an unmapped customer id", async () => {
    expect(await findUserByStripeCustomerId("cus_unknown")).toBeNull();
  });

  it("rejects two users mapped to the same stripe_customer_id", async () => {
    const a = await createUser({ email: "dupecus1@example.com", passwordHash: "h" });
    const b = await createUser({ email: "dupecus2@example.com", passwordHash: "h" });
    await setStripeCustomerId(a.id, "cus_shared");
    await expect(setStripeCustomerId(b.id, "cus_shared")).rejects.toThrow();
  });

  it("markTrialConsumed sets trial_consumed_at once and never overwrites it on a later call", async () => {
    const user = await createUser({ email: "trialonce@example.com", passwordHash: "h" });
    await markTrialConsumed(user.id);
    const first = (await findUserById(user.id))!.trial_consumed_at;
    expect(first).not.toBeNull();

    await markTrialConsumed(user.id); // second call, e.g. from a second webhook delivery
    expect((await findUserById(user.id))!.trial_consumed_at).toBe(first);
  });

  it("setBetaAccess(true) records both granted_at and granted_by", async () => {
    const admin = await createUser({ email: "admin-beta@example.com", passwordHash: "h" });
    const member = await createUser({ email: "member-beta@example.com", passwordHash: "h" });
    await setBetaAccess(member.id, true, admin.id);
    const reloaded = (await findUserById(member.id))!;
    expect(reloaded.beta_access_granted_at).not.toBeNull();
    expect(reloaded.beta_access_granted_by).toBe(admin.id);
  });

  it("setBetaAccess(false) clears both columns", async () => {
    const admin = await createUser({ email: "admin-beta2@example.com", passwordHash: "h" });
    const member = await createUser({ email: "member-beta2@example.com", passwordHash: "h" });
    await setBetaAccess(member.id, true, admin.id);
    await setBetaAccess(member.id, false, null);
    const reloaded = (await findUserById(member.id))!;
    expect(reloaded.beta_access_granted_at).toBeNull();
    expect(reloaded.beta_access_granted_by).toBeNull();
  });
});
