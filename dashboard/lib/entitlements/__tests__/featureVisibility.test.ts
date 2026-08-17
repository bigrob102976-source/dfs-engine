import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { setFeatureFlagState } from "@/lib/db/featureFlags";
import { insertSubscription } from "@/lib/db/subscriptions";
import { createUser, findUserById, updateUserRole } from "@/lib/db/users";

import { isFeatureVisibleToUser, listVisibleFeatureKeysForUser } from "../featureVisibility";

const KEY = "mlb.optimizer";

beforeEach(() => {
  __resetDbForTests();
});

function entitledMember() {
  const user = createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
  return user;
}

function admin() {
  const user = createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  updateUserRole(user.id, "ADMIN");
  // updateUserRole mutates the DB row, not this in-hand object -- re-fetch.
  return findUserById(user.id)!;
}

describe("isFeatureVisibleToUser", () => {
  it("PRODUCTION feature is visible to an entitled MEMBER", () => {
    expect(isFeatureVisibleToUser(entitledMember(), KEY)).toBe(true);
  });

  it("PRODUCTION feature is hidden from a MEMBER with no subscription/grant", () => {
    const user = createUser({ email: "unentitled@example.com", passwordHash: "h" });
    expect(isFeatureVisibleToUser(user, KEY)).toBe(false);
  });

  it("PRODUCTION feature is always visible to ADMIN, entitled or not", () => {
    expect(isFeatureVisibleToUser(admin(), KEY)).toBe(true);
  });

  it("DISABLED hides the feature from EVERYONE, including ADMIN", () => {
    setFeatureFlagState(KEY, "DISABLED", null);
    expect(isFeatureVisibleToUser(admin(), KEY)).toBe(false);
    expect(isFeatureVisibleToUser(entitledMember(), KEY)).toBe(false);
  });

  it("ADMIN_ONLY hides the feature from a MEMBER even with a full entitlement", () => {
    setFeatureFlagState(KEY, "ADMIN_ONLY", null);
    expect(isFeatureVisibleToUser(entitledMember(), KEY)).toBe(false);
    expect(isFeatureVisibleToUser(admin(), KEY)).toBe(true);
  });

  it("BETA behaves like PRODUCTION for entitlement gating", () => {
    setFeatureFlagState(KEY, "BETA", null);
    expect(isFeatureVisibleToUser(entitledMember(), KEY)).toBe(true);
    const unentitled = createUser({ email: "betauser@example.com", passwordHash: "h" });
    expect(isFeatureVisibleToUser(unentitled, KEY)).toBe(false);
  });

  it("a logged-out visitor (null) never sees any feature", () => {
    expect(isFeatureVisibleToUser(null, KEY)).toBe(false);
  });

  it("an unknown feature key is never visible", () => {
    expect(isFeatureVisibleToUser(admin(), "mlb.nonexistent_feature")).toBe(false);
  });
});

describe("listVisibleFeatureKeysForUser", () => {
  it("returns every seeded key for an admin", () => {
    const keys = listVisibleFeatureKeysForUser(admin());
    expect(keys.has("mlb.optimizer")).toBe(true);
    expect(keys.has("mlb.research")).toBe(true);
    expect(keys.size).toBeGreaterThan(5);
  });

  it("returns an empty set for a logged-out visitor", () => {
    expect(listVisibleFeatureKeysForUser(null).size).toBe(0);
  });
});
