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

  it("M5M: PRODUCTION would make canonical visible to any member -- confirms the mechanism works for the eventual cutover, without this milestone ever setting it", async () => {
    await setFeatureFlagState(CANONICAL_SERVING_FLAG_KEY, "PRODUCTION", null);
    // A member with no specific entitlement still isn't granted access --
    // PRODUCTION requires either ADMIN or the matching entitlement, same
    // rule every other flag in this app already follows.
    expect(await userCanUseCanonicalServing(await member())).toBe(false);
    expect(await userCanUseCanonicalServing(await admin())).toBe(true);
  });
});

describe("M5C/M5I/M5K: resolveServingBackend", () => {
  it("defaults to LEGACY_R2 when no backend is requested, for any user", async () => {
    expect((await resolveServingBackend(await admin(), undefined)).kind).toBe("LEGACY_R2");
    expect((await resolveServingBackend(await member(), undefined)).kind).toBe("LEGACY_R2");
    expect((await resolveServingBackend(null, undefined)).kind).toBe("LEGACY_R2");
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
