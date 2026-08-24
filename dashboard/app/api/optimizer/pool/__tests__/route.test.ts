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

const mockLoadPool = vi.fn();
vi.mock("@/lib/optimizerWorkspace/poolCache", () => ({
  loadPool: (...args: unknown[]) => mockLoadPool(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { getTodayChicagoDate } = await import("@/lib/currentDate");
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/optimizer/pool", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function loginAsMember() {
  const user = await createUser({ email: "member@example.com", passwordHash: "h" });
  await establishSession(user.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockLoadPool.mockReset();
  mockLoadPool.mockResolvedValue({ date: "irrelevant", slateId: "s1", players: [] });
});

describe("POST /api/optimizer/pool -- Milestone 31.2C date handling", () => {
  it("omitted date falls back to today's America/Chicago date (backward compatible)", async () => {
    await loginAsMember();
    const res = await POST(req({ slateId: "dkunofficial-152400" }));
    expect(res.status).toBe(200);
    expect(mockLoadPool).toHaveBeenCalledWith(getTodayChicagoDate(), "dkunofficial-152400", false);
  });

  it("an explicit valid date is used as-is, not forced to today", async () => {
    await loginAsMember();
    const res = await POST(req({ slateId: "dkunofficial-152400", date: "2026-08-21" }));
    expect(res.status).toBe(200);
    expect(mockLoadPool).toHaveBeenCalledWith("2026-08-21", "dkunofficial-152400", false);
  });

  it("rejects a malformed explicit date with 400 rather than silently using today", async () => {
    await loginAsMember();
    const res = await POST(req({ slateId: "dkunofficial-152400", date: "not-a-date" }));
    expect(res.status).toBe(400);
    expect(mockLoadPool).not.toHaveBeenCalled();
  });

  it("rejects an invalid calendar date (shape-valid but not real) with 400", async () => {
    await loginAsMember();
    const res = await POST(req({ slateId: "dkunofficial-152400", date: "2026-02-30" }));
    expect(res.status).toBe(400);
    expect(mockLoadPool).not.toHaveBeenCalled();
  });

  it("still requires slateId", async () => {
    await loginAsMember();
    const res = await POST(req({ date: "2026-08-21" }));
    expect(res.status).toBe(400);
    expect(mockLoadPool).not.toHaveBeenCalled();
  });
});
