import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import {
  countAdmins,
  countUsers,
  createUser,
  findUserByEmail,
  findUserById,
  findUserByStripeCustomerId,
  listUsers,
  markTrialConsumed,
  setStripeCustomerId,
  setUserDisabled,
  updateUserRole,
} from "../users";

beforeEach(() => {
  __resetDbForTests();
});

describe("users", () => {
  it("creates a user with default role MEMBER", () => {
    const user = createUser({ email: "test@example.com", passwordHash: "hash" });
    expect(user.role).toBe("MEMBER");
    expect(user.email).toBe("test@example.com");
    expect(user.email_verified_at).toBeNull();
  });

  it("finds a user by email case-insensitively", () => {
    createUser({ email: "Test@Example.com", passwordHash: "hash" });
    expect(findUserByEmail("test@example.com")).not.toBeNull();
    expect(findUserByEmail("TEST@EXAMPLE.COM")).not.toBeNull();
  });

  it("returns null for an unknown email or id", () => {
    expect(findUserByEmail("nobody@example.com")).toBeNull();
    expect(findUserById("no-such-id")).toBeNull();
  });

  it("rejects a duplicate email", () => {
    createUser({ email: "dupe@example.com", passwordHash: "hash" });
    expect(() => createUser({ email: "dupe@example.com", passwordHash: "hash2" })).toThrow();
  });

  it("updateUserRole persists the new role", () => {
    const user = createUser({ email: "promote@example.com", passwordHash: "hash" });
    updateUserRole(user.id, "ADMIN");
    expect(findUserById(user.id)!.role).toBe("ADMIN");
  });

  it("countAdmins reflects role changes", () => {
    expect(countAdmins()).toBe(0);
    const user = createUser({ email: "admin@example.com", passwordHash: "hash" });
    updateUserRole(user.id, "ADMIN");
    expect(countAdmins()).toBe(1);
  });

  it("setUserDisabled sets and clears disabled_at", () => {
    const user = createUser({ email: "disable@example.com", passwordHash: "hash" });
    setUserDisabled(user.id, true);
    expect(findUserById(user.id)!.disabled_at).not.toBeNull();
    setUserDisabled(user.id, false);
    expect(findUserById(user.id)!.disabled_at).toBeNull();
  });

  it("listUsers filters by search and role", () => {
    const a = createUser({ email: "alpha@example.com", passwordHash: "h", displayName: "Alpha" });
    createUser({ email: "beta@example.com", passwordHash: "h", displayName: "Beta" });
    updateUserRole(a.id, "ADMIN");

    expect(listUsers({ search: "alpha" }).map((u) => u.email)).toEqual(["alpha@example.com"]);
    expect(listUsers({ role: "ADMIN" }).map((u) => u.email)).toEqual(["alpha@example.com"]);
    expect(listUsers({}).length).toBe(2);
  });

  it("countUsers matches listUsers filtering", () => {
    createUser({ email: "one@example.com", passwordHash: "h" });
    createUser({ email: "two@example.com", passwordHash: "h" });
    expect(countUsers({})).toBe(2);
    expect(countUsers({ search: "one" })).toBe(1);
  });

  it("a new user has null stripe_customer_id and trial_consumed_at", () => {
    const user = createUser({ email: "fresh@example.com", passwordHash: "h" });
    expect(user.stripe_customer_id).toBeNull();
    expect(user.trial_consumed_at).toBeNull();
  });

  it("setStripeCustomerId / findUserByStripeCustomerId round-trip", () => {
    const user = createUser({ email: "cus@example.com", passwordHash: "h" });
    setStripeCustomerId(user.id, "cus_abc123");
    expect(findUserById(user.id)!.stripe_customer_id).toBe("cus_abc123");
    expect(findUserByStripeCustomerId("cus_abc123")?.id).toBe(user.id);
  });

  it("findUserByStripeCustomerId returns null for an unmapped customer id", () => {
    expect(findUserByStripeCustomerId("cus_unknown")).toBeNull();
  });

  it("rejects two users mapped to the same stripe_customer_id", () => {
    const a = createUser({ email: "dupecus1@example.com", passwordHash: "h" });
    const b = createUser({ email: "dupecus2@example.com", passwordHash: "h" });
    setStripeCustomerId(a.id, "cus_shared");
    expect(() => setStripeCustomerId(b.id, "cus_shared")).toThrow();
  });

  it("markTrialConsumed sets trial_consumed_at once and never overwrites it on a later call", () => {
    const user = createUser({ email: "trialonce@example.com", passwordHash: "h" });
    markTrialConsumed(user.id);
    const first = findUserById(user.id)!.trial_consumed_at;
    expect(first).not.toBeNull();

    markTrialConsumed(user.id); // second call, e.g. from a second webhook delivery
    expect(findUserById(user.id)!.trial_consumed_at).toBe(first);
  });
});
