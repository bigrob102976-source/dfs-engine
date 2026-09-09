import { beforeEach, describe, expect, it } from "vitest";

import { __resetDbForTests } from "../../db/client";
import { __resetExecutorForTests } from "../../db/executor";
import { setFeatureFlagState } from "../../db/featureFlags";
import { createUser, findUserById, updateUserRole } from "../../db/users";
import { CANONICAL_SERVING_FLAG_KEY, resolveServingBackend, userCanUseCanonicalServing } from "../config";

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
});

async function member() {
  return createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
}

async function admin() {
  const user = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(user.id, "ADMIN");
  return (await findUserById(user.id))!;
}

describe("M5C/M5I: userCanUseCanonicalServing", () => {
  it("is seeded ADMIN_ONLY -- true for ADMIN, false for a plain MEMBER, out of the box", async () => {
    expect(await userCanUseCanonicalServing(await admin())).toBe(true);
    expect(await userCanUseCanonicalServing(await member())).toBe(false);
  });

  it("is false for an unauthenticated (null) user", async () => {
    expect(await userCanUseCanonicalServing(null)).toBe(false);
  });

  it("DISABLED refuses canonical serving even for ADMIN -- the full kill switch", async () => {
    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "DISABLED", null);
    expect(await userCanUseCanonicalServing(await admin())).toBe(false);
  });

  it("PRODUCTION grants canonical to a plain MEMBER with no entitlement -- serving backend is infrastructure, not a purchased feature", async () => {
    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "PRODUCTION", null);
    // Regression guard for the 2026-09-08 outage: the subscriptions table
    // is empty in production, so requiring a per-user entitlement here
    // pinned all 47 members to the broken legacy backend.
    expect(await userCanUseCanonicalServing(await member())).toBe(true);
    expect(await userCanUseCanonicalServing(await admin())).toBe(true);
  });

  it("PRODUCTION still refuses an unauthenticated (null) user", async () => {
    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "PRODUCTION", null);
    expect(await userCanUseCanonicalServing(null)).toBe(false);
  });

  it("DISABLED remains a full kill switch even from PRODUCTION -- config-only rollback for every user", async () => {
    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "PRODUCTION", null);
    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "DISABLED", null);
    expect(await userCanUseCanonicalServing(await member())).toBe(false);
    expect(await userCanUseCanonicalServing(await admin())).toBe(false);
  });
});

describe("M5C/M5I/M5K: resolveServingBackend", () => {
  it("defaults to CANONICAL_POSTGRES for a user the flag covers, and LEGACY_R2 for everyone else -- no request param required", async () => {
    // The whole point of the 2026-09-08 fix: no customer-facing page ever
    // sent a `servingBackend` param, so requiring one meant the flag being
    // PRODUCTION did nothing for real traffic. The default must now follow
    // the flag, not the caller.
    expect((await resolveServingBackend(await admin(), undefined)).kind).toBe("CANONICAL_POSTGRES");
    expect((await resolveServingBackend(await member(), undefined)).kind).toBe("LEGACY_R2");
    expect((await resolveServingBackend(null, undefined)).kind).toBe("LEGACY_R2");
  });

  it("honors an explicit LEGACY_R2 request even from a user the flag covers -- the per-request escape hatch", async () => {
    expect((await resolveServingBackend(await admin(), "LEGACY_R2")).kind).toBe("LEGACY_R2");
  });

  it("honors an explicit CANONICAL_POSTGRES request from an ADMIN", async () => {
    expect((await resolveServingBackend(await admin(), "CANONICAL_POSTGRES")).kind).toBe("CANONICAL_POSTGRES");
  });

  it("M5I: a MEMBER's explicit CANONICAL_POSTGRES request is silently refused -- LEGACY_R2 every time, no override possible", async () => {
    expect((await resolveServingBackend(await member(), "CANONICAL_POSTGRES")).kind).toBe("LEGACY_R2");
  });

  it("M5L rollback: once the flag is set DISABLED, even an ADMIN's explicit request falls back to LEGACY_R2 -- config-only rollback, no code change", async () => {
    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "DISABLED", null);
    expect((await resolveServingBackend(await admin(), "CANONICAL_POSTGRES")).kind).toBe("LEGACY_R2");
  });
});
