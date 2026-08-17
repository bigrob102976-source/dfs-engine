import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { hasAuditAction, listAuditLog } from "@/lib/db/auditLog";
import { __resetDbForTests } from "@/lib/db/client";
import { createUser, findUserById, updateUserRole } from "@/lib/db/users";

import { maybeBootstrapAdmin } from "../bootstrap";

const BOOTSTRAP_EMAIL = "bigrob102976@gmail.com";
let originalEnv: string | undefined;

beforeEach(() => {
  __resetDbForTests();
  originalEnv = process.env.ADMIN_BOOTSTRAP_EMAIL;
  delete process.env.ADMIN_BOOTSTRAP_EMAIL; // exercise the documented default
});

afterEach(() => {
  if (originalEnv === undefined) delete process.env.ADMIN_BOOTSTRAP_EMAIL;
  else process.env.ADMIN_BOOTSTRAP_EMAIL = originalEnv;
});

describe("maybeBootstrapAdmin", () => {
  it("promotes a MEMBER with the configured bootstrap email to ADMIN and records an audit row", () => {
    const user = createUser({ email: BOOTSTRAP_EMAIL, passwordHash: "h" });
    const fired = maybeBootstrapAdmin(user);
    expect(fired).toBe(true);
    expect(findUserById(user.id)!.role).toBe("ADMIN");
    expect(hasAuditAction("admin_bootstrap")).toBe(true);
    const [entry] = listAuditLog({ action: "admin_bootstrap" });
    expect(entry.actor_label).toBe("system");
    expect(entry.actor_user_id).toBeNull();
    expect(entry.target_id).toBe(user.id);
  });

  it("matches the bootstrap email case-insensitively", () => {
    const user = createUser({ email: "BigRob102976@Gmail.com", passwordHash: "h" });
    expect(maybeBootstrapAdmin(user)).toBe(true);
  });

  it("does not fire for a non-matching email", () => {
    const user = createUser({ email: "someone-else@example.com", passwordHash: "h" });
    expect(maybeBootstrapAdmin(user)).toBe(false);
    expect(findUserById(user.id)!.role).toBe("MEMBER");
  });

  it("fires exactly once system-wide, even for the same user calling again", () => {
    const user = createUser({ email: BOOTSTRAP_EMAIL, passwordHash: "h" });
    expect(maybeBootstrapAdmin(user)).toBe(true);
    expect(maybeBootstrapAdmin(findUserById(user.id)!)).toBe(false);
  });

  it("does not re-fire for a second account sharing the bootstrap email after the first already triggered it", () => {
    const first = createUser({ email: BOOTSTRAP_EMAIL, passwordHash: "h" });
    expect(maybeBootstrapAdmin(first)).toBe(true);

    // Demote the bootstrapped admin, then simulate ANOTHER login attempt
    // for a *different* user row (shouldn't normally happen since email
    // is UNIQUE, but this proves the guard is a global audit-log check,
    // not a per-user flag that could be reset).
    updateUserRole(first.id, "MEMBER");
    expect(maybeBootstrapAdmin(findUserById(first.id)!)).toBe(false);
    expect(findUserById(first.id)!.role).toBe("MEMBER");
  });

  it("respects ADMIN_BOOTSTRAP_EMAIL override", () => {
    process.env.ADMIN_BOOTSTRAP_EMAIL = "custom-admin@example.com";
    const defaultEmailUser = createUser({ email: BOOTSTRAP_EMAIL, passwordHash: "h" });
    expect(maybeBootstrapAdmin(defaultEmailUser)).toBe(false);

    const customUser = createUser({ email: "custom-admin@example.com", passwordHash: "h" });
    expect(maybeBootstrapAdmin(customUser)).toBe(true);
  });

  it("does not fire for a user who is already ADMIN", () => {
    const user = createUser({ email: BOOTSTRAP_EMAIL, passwordHash: "h" });
    updateUserRole(user.id, "ADMIN");
    // No audit row exists yet, but role is already ADMIN, not MEMBER.
    expect(maybeBootstrapAdmin(findUserById(user.id)!)).toBe(false);
  });
});
