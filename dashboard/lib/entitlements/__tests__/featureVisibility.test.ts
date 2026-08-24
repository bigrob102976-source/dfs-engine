import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "@/lib/db/client";
import { __resetExecutorForTests } from "@/lib/db/executor";
import { setFeatureFlagState } from "@/lib/db/featureFlags";
import { insertSubscription } from "@/lib/db/subscriptions";
import { createUser, findUserById, updateUserRole } from "@/lib/db/users";

import { isFeatureVisibleToUser, listVisibleFeatureKeysForUser } from "../featureVisibility";

const KEY = "mlb.optimizer";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

async function entitledMember() {
  const user = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await insertSubscription({ userId: user.id, planId: "weekly", status: "active" });
  return user;
}

async function admin() {
  const user = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(user.id, "ADMIN");
  // updateUserRole mutates the DB row, not this in-hand object -- re-fetch.
  return (await findUserById(user.id))!;
}

describe("isFeatureVisibleToUser", () => {
  it("PRODUCTION feature is visible to an entitled MEMBER", async () => {
    expect(await isFeatureVisibleToUser(await entitledMember(), KEY)).toBe(true);
  });

  it("PRODUCTION feature is hidden from a MEMBER with no subscription/grant", async () => {
    const user = await createUser({ email: "unentitled@example.com", passwordHash: "h" });
    expect(await isFeatureVisibleToUser(user, KEY)).toBe(false);
  });

  it("PRODUCTION feature is always visible to ADMIN, entitled or not", async () => {
    expect(await isFeatureVisibleToUser(await admin(), KEY)).toBe(true);
  });

  it("DISABLED hides the feature from EVERYONE, including ADMIN", async () => {
    await setFeatureFlagState(KEY, "DISABLED", null);
    expect(await isFeatureVisibleToUser(await admin(), KEY)).toBe(false);
    expect(await isFeatureVisibleToUser(await entitledMember(), KEY)).toBe(false);
  });

  it("ADMIN_ONLY hides the feature from a MEMBER even with a full entitlement", async () => {
    await setFeatureFlagState(KEY, "ADMIN_ONLY", null);
    expect(await isFeatureVisibleToUser(await entitledMember(), KEY)).toBe(false);
    expect(await isFeatureVisibleToUser(await admin(), KEY)).toBe(true);
  });

  it("BETA behaves like PRODUCTION for entitlement gating", async () => {
    await setFeatureFlagState(KEY, "BETA", null);
    expect(await isFeatureVisibleToUser(await entitledMember(), KEY)).toBe(true);
    const unentitled = await createUser({ email: "betauser@example.com", passwordHash: "h" });
    expect(await isFeatureVisibleToUser(unentitled, KEY)).toBe(false);
  });

  it("a logged-out visitor (null) never sees any feature", async () => {
    expect(await isFeatureVisibleToUser(null, KEY)).toBe(false);
  });

  it("an unknown feature key is never visible", async () => {
    expect(await isFeatureVisibleToUser(await admin(), "mlb.nonexistent_feature")).toBe(false);
  });
});

describe("listVisibleFeatureKeysForUser", () => {
  it("returns every seeded key for an admin", async () => {
    const keys = await listVisibleFeatureKeysForUser(await admin());
    expect(keys.has("mlb.optimizer")).toBe(true);
    expect(keys.has("mlb.research")).toBe(true);
    expect(keys.size).toBeGreaterThan(5);
  });

  it("returns an empty set for a logged-out visitor", async () => {
    expect((await listVisibleFeatureKeysForUser(null)).size).toBe(0);
  });
});
