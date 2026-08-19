import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { hasProductAccess } from "../betaAccess";
import type { CurrentUser } from "../session";

const ENV_KEY = "PRIVATE_BETA";
let originalValue: string | undefined;

beforeEach(() => {
  originalValue = process.env[ENV_KEY];
});

afterEach(() => {
  if (originalValue === undefined) delete (process.env as Record<string, string | undefined>)[ENV_KEY];
  else (process.env as Record<string, string | undefined>)[ENV_KEY] = originalValue;
});

function member(betaAccessGrantedAt: string | null): CurrentUser {
  return { id: "u1", email: "m@example.com", role: "MEMBER", displayName: null, emailVerifiedAt: null, betaAccessGrantedAt };
}

function admin(): CurrentUser {
  return { id: "a1", email: "a@example.com", role: "ADMIN", displayName: null, emailVerifiedAt: null, betaAccessGrantedAt: null };
}

describe("hasProductAccess", () => {
  it("is true for everyone when PRIVATE_BETA is not set (default, unaffected behavior)", () => {
    delete (process.env as Record<string, string | undefined>)[ENV_KEY];
    expect(hasProductAccess(member(null))).toBe(true);
  });

  it("is true for everyone when PRIVATE_BETA is set to something other than 'true'", () => {
    (process.env as Record<string, string | undefined>)[ENV_KEY] = "false";
    expect(hasProductAccess(member(null))).toBe(true);
  });

  it("when PRIVATE_BETA=true: ADMIN always has access regardless of beta grant", () => {
    (process.env as Record<string, string | undefined>)[ENV_KEY] = "true";
    expect(hasProductAccess(admin())).toBe(true);
  });

  it("when PRIVATE_BETA=true: a MEMBER without a grant has no access", () => {
    (process.env as Record<string, string | undefined>)[ENV_KEY] = "true";
    expect(hasProductAccess(member(null))).toBe(false);
  });

  it("when PRIVATE_BETA=true: a MEMBER with a grant has access", () => {
    (process.env as Record<string, string | undefined>)[ENV_KEY] = "true";
    expect(hasProductAccess(member("2026-08-19T00:00:00.000Z"))).toBe(true);
  });
});
