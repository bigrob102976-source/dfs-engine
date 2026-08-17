import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../client";
import { countAdmins, countUsers, createUser, findUserByEmail, findUserById, listUsers, setUserDisabled, updateUserRole } from "../users";

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
});
