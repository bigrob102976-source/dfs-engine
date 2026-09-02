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

const mockCompute = vi.fn();
vi.mock("@/lib/db/canonicalEligibility", () => ({
  computeAndPersistEligibilityForSlate: (...args: unknown[]) => mockCompute(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { POST } = await import("../route");

function req(body: unknown) {
  return new Request("http://localhost/api/admin/canonical-eligibility", {
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
  mockCompute.mockReset();
  mockCompute.mockResolvedValue({ status: "OK", playersUpdated: 5 });
});

describe("M6: /api/admin/canonical-eligibility access control", () => {
  it("401s with no session", async () => {
    const res = await POST(req({ internalSlateId: "s1" }));
    expect(res.status).toBe(401);
    expect(mockCompute).not.toHaveBeenCalled();
  });

  it("403s for a logged-in MEMBER", async () => {
    await loginAsMember();
    const res = await POST(req({ internalSlateId: "s1" }));
    expect(res.status).toBe(403);
    expect(mockCompute).not.toHaveBeenCalled();
  });

  it("400s for a missing internalSlateId", async () => {
    await loginAsAdmin();
    const res = await POST(req({}));
    expect(res.status).toBe(400);
    expect(mockCompute).not.toHaveBeenCalled();
  });

  it("200s for an ADMIN and returns the real computation result", async () => {
    await loginAsAdmin();
    const res = await POST(req({ internalSlateId: "s1" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.result.status).toBe("OK");
    expect(mockCompute).toHaveBeenCalledWith("s1");
  });

  it("404s when the slate is not found", async () => {
    await loginAsAdmin();
    mockCompute.mockResolvedValue({ status: "SLATE_NOT_FOUND", playersUpdated: 0 });
    const res = await POST(req({ internalSlateId: "nope" }));
    expect(res.status).toBe(404);
  });
});
