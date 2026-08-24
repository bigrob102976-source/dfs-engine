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
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { getSport } = await import("@/lib/db/sports");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { PATCH: setStatus } = await import("../[code]/status/route");

function ctx(code: string) {
  return { params: Promise.resolve({ code }) };
}

function patchRequest(status: unknown) {
  return new Request("http://localhost/x", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ status }) });
}

async function loginAsAdmin() {
  const admin = await createUser({ email: "admin@example.com", passwordHash: "h" });
  await updateUserRole(admin.id, "ADMIN");
  await establishSession(admin.id, null);
  return admin;
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("PATCH /api/admin/sports/[code]/status", () => {
  it("403s for a MEMBER", async () => {
    const member = await createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await setStatus(patchRequest("LIVE"), ctx("NFL"));
    expect(res.status).toBe(403);
  });

  it("404s for an unknown sport code", async () => {
    await loginAsAdmin();
    const res = await setStatus(patchRequest("LIVE"), ctx("NOPE"));
    expect(res.status).toBe(404);
  });

  it("400s for an invalid status value", async () => {
    await loginAsAdmin();
    const res = await setStatus(patchRequest("SORT_OF_LIVE"), ctx("NFL"));
    expect(res.status).toBe(400);
  });

  it("flips NFL to LIVE and writes an audit row", async () => {
    const admin = await loginAsAdmin();
    expect((await getSport("NFL"))?.status).toBe("COMING_SOON");

    const res = await setStatus(patchRequest("LIVE"), ctx("NFL"));
    expect(res.status).toBe(200);
    expect((await getSport("NFL"))?.status).toBe("LIVE");

    const entries = await listAuditLog({ action: "sport_status_changed" });
    expect(entries).toHaveLength(1);
    expect(entries[0].actor_user_id).toBe(admin.id);
    expect(entries[0].target_id).toBe("NFL");
  });
});
