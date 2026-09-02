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

const mockCheck = vi.fn();
vi.mock("@/lib/db/canonicalLineupLegalityCheck", () => ({
  checkCanonicalLineupLegality: (...args: unknown[]) => mockCheck(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/admin/canonical-lineup-check", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
}

async function loginAsAdmin() {
  const admin = await createUser({ email: `admin-${Math.random()}@example.com`, passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
}

async function loginAsMember() {
  const member = await createUser({ email: `member-${Math.random()}@example.com`, passwordHash: "h" });
  await establishSession(member.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockCheck.mockReset();
  mockCheck.mockResolvedValue({ status: "OK", lineupsRequested: 1, lineupsProduced: 1, lineups: [[]] });
});

describe("M6L: /api/admin/canonical-lineup-check access control", () => {
  it("401s with no session", async () => {
    const res = await POST(req({ internalSlateId: "s1" }));
    expect(res.status).toBe(401);
  });

  it("403s for a logged-in MEMBER", async () => {
    await loginAsMember();
    const res = await POST(req({ internalSlateId: "s1" }));
    expect(res.status).toBe(403);
  });

  it("400s for a missing internalSlateId", async () => {
    await loginAsAdmin();
    const res = await POST(req({}));
    expect(res.status).toBe(400);
  });

  it("200s for an ADMIN and returns real results", async () => {
    await loginAsAdmin();
    const res = await POST(req({ internalSlateId: "s1", count: 2, locks: ["1"], excludes: ["2"] }));
    expect(res.status).toBe(200);
    expect(mockCheck).toHaveBeenCalledWith("s1", { count: 2, locks: ["1"], excludes: ["2"] });
  });

  it("404s when the slate is not found", async () => {
    await loginAsAdmin();
    mockCheck.mockResolvedValue({ status: "SLATE_NOT_FOUND", lineupsRequested: 1, lineupsProduced: 0, lineups: [] });
    const res = await POST(req({ internalSlateId: "nope" }));
    expect(res.status).toBe(404);
  });
});
