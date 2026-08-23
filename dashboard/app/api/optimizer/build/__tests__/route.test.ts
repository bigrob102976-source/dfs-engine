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

const mockBuildLineups = vi.fn();
vi.mock("@/lib/optimizerWorkspace/buildRunner", () => ({
  buildLineups: (...args: unknown[]) => mockBuildLineups(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/optimizer/build", {
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
  mockBuildLineups.mockReset();
  mockBuildLineups.mockResolvedValue({
    ok: true, errors: [], coverage: null, lineupSetPath: "x.json", csvPath: "x.csv", lineupsRequested: 1, lineupsGenerated: 1,
    stoppedReason: null, lineups: [], elapsedMs: 10, excludedMissingProjectionSource: [],
  });
});

describe("POST /api/optimizer/build -- Milestone 32.4 Big Money ML admin gating", () => {
  it("a MEMBER can still build with every pre-existing projection source", async () => {
    await loginAsMember();
    for (const projectionSource of ["independent", "native", "ai", "fantasypros", "external", "adjusted"]) {
      const res = await POST(req(baseBody({ projectionSource })));
      expect(res.status).toBe(200);
    }
  });

  it("a MEMBER is rejected with 403 when selecting big_money_ml", async () => {
    await loginAsMember();
    const res = await POST(req(baseBody({ projectionSource: "big_money_ml" })));
    expect(res.status).toBe(403);
    expect(mockBuildLineups).not.toHaveBeenCalled();
  });

  it("an ADMIN can select big_money_ml", async () => {
    await loginAsAdmin();
    const res = await POST(req(baseBody({ projectionSource: "big_money_ml" })));
    expect(res.status).toBe(200);
    expect(mockBuildLineups).toHaveBeenCalledTimes(1);
  });

  it("an unauthenticated request is rejected with 401 before any source check", async () => {
    const res = await POST(req(baseBody({ projectionSource: "big_money_ml" })));
    expect(res.status).toBe(401);
    expect(mockBuildLineups).not.toHaveBeenCalled();
  });
});
