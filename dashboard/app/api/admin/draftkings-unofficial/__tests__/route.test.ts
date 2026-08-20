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

const mockLoad = vi.fn();
vi.mock("@/lib/draftKingsUnofficialExplorer", () => ({
  loadDkUnofficialExplorerData: (...args: unknown[]) => mockLoad(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { GET } = await import("../route");

function req(query: string) {
  return new Request(`http://localhost/api/admin/draftkings-unofficial${query}`);
}

async function loginAsAdmin() {
  const admin = createUser({ email: "admin@example.com", passwordHash: "h" });
  updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
}

async function loginAsMember() {
  const user = createUser({ email: "member@example.com", passwordHash: "h" });
  await establishSession(user.id, null);
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
  mockLoad.mockReset();
});

describe("GET /api/admin/draftkings-unofficial", () => {
  it("rejects an unauthenticated request", async () => {
    const res = await GET(req("?sport=MLB"));
    expect(res.status).toBe(401);
    expect(mockLoad).not.toHaveBeenCalled();
  });

  it("rejects a non-admin member", async () => {
    await loginAsMember();
    const res = await GET(req("?sport=MLB"));
    expect(res.status).toBe(403);
    expect(mockLoad).not.toHaveBeenCalled();
  });

  it("requires a sport query param", async () => {
    await loginAsAdmin();
    const res = await GET(req(""));
    expect(res.status).toBe(400);
    expect(mockLoad).not.toHaveBeenCalled();
  });

  it("rejects a non-numeric draftGroupId", async () => {
    await loginAsAdmin();
    const res = await GET(req("?sport=MLB&draftGroupId=abc"));
    expect(res.status).toBe(400);
    expect(mockLoad).not.toHaveBeenCalled();
  });

  it("passes sport/draftGroupId/gameTypeId through to the loader", async () => {
    await loginAsAdmin();
    mockLoad.mockResolvedValue({ status: "ok", sport: "MLB", slates: [] });
    const res = await GET(req("?sport=MLB&draftGroupId=152389&gameTypeId=2"));
    expect(res.status).toBe(200);
    expect(mockLoad).toHaveBeenCalledWith("MLB", 152389, 2);
  });

  it("returns the not_enabled status honestly, not an error", async () => {
    await loginAsAdmin();
    mockLoad.mockResolvedValue({ status: "not_enabled", detail: "Set DK_UNOFFICIAL_ENABLED=true" });
    const res = await GET(req("?sport=MLB"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("not_enabled");
  });

  it("returns 502 when the loader itself fails", async () => {
    await loginAsAdmin();
    mockLoad.mockResolvedValue({ error: "python script crashed" });
    const res = await GET(req("?sport=MLB"));
    expect(res.status).toBe(502);
  });
});
