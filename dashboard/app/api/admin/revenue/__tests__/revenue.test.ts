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

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET: getRevenue } = await import("../route");

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
});

describe("GET /api/admin/revenue", () => {
  it("401s with no session", async () => {
    expect((await getRevenue()).status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    expect((await getRevenue()).status).toBe(403);
  });

  it("returns real revenue figures for an ADMIN", async () => {
    const admin = createUser({ email: "admin@example.com", passwordHash: "h" });
    updateUserRole(admin.id, "ADMIN");
    await establishSession(admin.id, null);

    const res = await getRevenue();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.mrrCents).toBe(0);
    expect(body.churnRatePct).toBeNull();
  });
});
