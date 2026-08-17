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
const { getFeatureFlag } = await import("@/lib/db/featureFlags");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { PATCH: setState } = await import("../[key]/state/route");

function ctx(key: string) {
  return { params: Promise.resolve({ key }) };
}

function patchRequest(state: unknown) {
  return new Request("http://localhost/x", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ state }) });
}

async function loginAsAdmin() {
  const admin = createUser({ email: "admin@example.com", passwordHash: "h" });
  updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return admin;
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
});

describe("PATCH /api/admin/features/[key]/state", () => {
  it("403s for a MEMBER", async () => {
    const member = createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await setState(patchRequest("DISABLED"), ctx("mlb.optimizer"));
    expect(res.status).toBe(403);
  });

  it("404s for an unknown key", async () => {
    await loginAsAdmin();
    const res = await setState(patchRequest("DISABLED"), ctx("not.a.key"));
    expect(res.status).toBe(404);
  });

  it("400s for an invalid state value", async () => {
    await loginAsAdmin();
    const res = await setState(patchRequest("SOMEWHAT_ON"), ctx("mlb.optimizer"));
    expect(res.status).toBe(400);
  });

  it("disables a feature (real kill-switch) and writes an audit row", async () => {
    const admin = await loginAsAdmin();
    expect(getFeatureFlag("mlb.optimizer")?.state).toBe("PRODUCTION");

    const res = await setState(patchRequest("DISABLED"), ctx("mlb.optimizer"));
    expect(res.status).toBe(200);
    expect(getFeatureFlag("mlb.optimizer")?.state).toBe("DISABLED");

    const entries = listAuditLog({ action: "feature_flag_changed" });
    expect(entries).toHaveLength(1);
    expect(entries[0].actor_user_id).toBe(admin.id);
    expect(entries[0].target_id).toBe("mlb.optimizer");
  });
});
