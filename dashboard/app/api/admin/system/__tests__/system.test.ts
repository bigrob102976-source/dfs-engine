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

const mockExternalStatus = vi.fn();
const mockGameEnvStatus = vi.fn();
const mockMockMode = vi.fn();
vi.mock("@/lib/externalProjectionsStatus", () => ({ getExternalProjectionsStatus: (...args: unknown[]) => mockExternalStatus(...args) }));
vi.mock("@/lib/gameEnvironmentStatus", () => ({ getGameEnvironmentStatus: (...args: unknown[]) => mockGameEnvStatus(...args) }));
vi.mock("@/lib/mockMode", () => ({ getMockModeEnabled: () => mockMockMode() }));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET: getSystem } = await import("../route");

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
  mockExternalStatus.mockResolvedValue({ error: "unavailable in test" });
  mockGameEnvStatus.mockResolvedValue({ error: "unavailable in test" });
  mockMockMode.mockResolvedValue(false);
});

describe("GET /api/admin/system", () => {
  it("401s with no session", async () => {
    const res = await getSystem();
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await getSystem();
    expect(res.status).toBe(403);
  });

  it("returns real DB stats + composed provider status for an ADMIN", async () => {
    const admin = createUser({ email: "admin@example.com", passwordHash: "h" });
    updateUserRole(admin.id, "ADMIN");
    await establishSession(admin.id, null);

    const res = await getSystem();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.db.totalUsers).toBe(1);
    expect(body.mockModeEnabled).toBe(false);
  });
});
