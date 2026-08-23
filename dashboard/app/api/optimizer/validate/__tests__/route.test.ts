import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieStore = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) => (cookieStore.has(name) ? { name, value: cookieStore.get(name)! } : undefined),
    set: (name: string, value: string) => {
      cookieStore.set(name, value);
    },
    delete: (name: string) => {
      cookieStore.delete(name);
    },
  }),
}));

const mockValidateBuildRequest = vi.fn();
vi.mock("@/lib/optimizerWorkspace/buildRunner", () => ({
  validateBuildRequest: (...args: unknown[]) => mockValidateBuildRequest(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/optimizer/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function baseBody(overrides: Record<string, unknown> = {}) {
  return { slateId: "dkunofficial-152543", lineups: 1, ...overrides };
}

async function loginAsMember() {
  const user = createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(user.id, null);
  return user;
}

async function loginAsAdmin() {
  const user = createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  updateUserRole(user.id, "ADMIN");
  await establishSession(user.id, null);
  return user;
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
  mockValidateBuildRequest.mockReset();
  mockValidateBuildRequest.mockResolvedValue({ errors: [], coverage: null });
});

describe("POST /api/optimizer/validate -- Milestone 32.4 Big Money ML admin gating", () => {
  it("a MEMBER can still validate every pre-existing projection source", async () => {
    await loginAsMember();
    const res = await POST(req(baseBody({ projectionSource: "native" })));
    expect(res.status).toBe(200);
  });

  it("a MEMBER is rejected with 403 when validating with big_money_ml selected", async () => {
    await loginAsMember();
    const res = await POST(req(baseBody({ projectionSource: "big_money_ml" })));
    expect(res.status).toBe(403);
    expect(mockValidateBuildRequest).not.toHaveBeenCalled();
  });

  it("an ADMIN can validate with big_money_ml selected", async () => {
    await loginAsAdmin();
    const res = await POST(req(baseBody({ projectionSource: "big_money_ml" })));
    expect(res.status).toBe(200);
    expect(mockValidateBuildRequest).toHaveBeenCalledTimes(1);
  });

  it("passes the coverage summary through in the response -- Milestone 32.6 Part 3", async () => {
    await loginAsMember();
    mockValidateBuildRequest.mockResolvedValue({
      errors: [],
      coverage: {
        poolSize: 60, optimizerEligible: 60, usableForBuild: 60,
        skippedMissingProjection: 0, excludedMissingSource: 0, projectionSource: "native", strictSource: false,
      },
    });
    const res = await POST(req(baseBody({ projectionSource: "native" })));
    const body = await res.json();
    expect(body.coverage.poolSize).toBe(60);
    expect(body.coverage.usableForBuild).toBe(60);
  });
});
