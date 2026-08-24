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

const mockGetBigMoneyMlCoverage = vi.fn();
vi.mock("@/lib/bigMoneyMlOptimizer", () => ({
  getBigMoneyMlCoverage: (...args: unknown[]) => mockGetBigMoneyMlCoverage(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET } = await import("../route");

async function loginAsMember() {
  const user = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(user.id, null);
}

async function loginAsAdmin() {
  const user = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(user.id, "ADMIN");
  await establishSession(user.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockGetBigMoneyMlCoverage.mockReset();
  mockGetBigMoneyMlCoverage.mockReturnValue({
    pitchers: { generated: 22, eligible: 22 }, hitters: { generated: 81, eligible: 81 },
    combined: { generated: 103, eligible: 103 }, gamesWaitingForLineups: 0,
    pitcherModelVersion: "1.0.0", hitterModelVersion: "1.0.0",
    pitcherSnapshotGeneratedAt: "2026-08-22T20:18:43+00:00", hitterSnapshotGeneratedAt: "2026-08-22T22:11:56+00:00",
  });
});

describe("GET /api/optimizer/ml-coverage", () => {
  it("rejects a MEMBER with 403", async () => {
    await loginAsMember();
    const res = await GET(new Request("http://localhost/api/optimizer/ml-coverage?date=2026-08-22&slateId=dkunofficial-152543"));
    expect(res.status).toBe(403);
    expect(mockGetBigMoneyMlCoverage).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request with 401", async () => {
    const res = await GET(new Request("http://localhost/api/optimizer/ml-coverage?date=2026-08-22"));
    expect(res.status).toBe(401);
  });

  it("returns coverage for an ADMIN", async () => {
    await loginAsAdmin();
    const res = await GET(new Request("http://localhost/api/optimizer/ml-coverage?date=2026-08-22&slateId=dkunofficial-152543"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.coverage.combined).toEqual({ generated: 103, eligible: 103 });
    expect(mockGetBigMoneyMlCoverage).toHaveBeenCalledWith("2026-08-22", "dkunofficial-152543");
  });

  it("rejects a malformed date with 400", async () => {
    await loginAsAdmin();
    const res = await GET(new Request("http://localhost/api/optimizer/ml-coverage?date=not-a-date"));
    expect(res.status).toBe(400);
  });
});
