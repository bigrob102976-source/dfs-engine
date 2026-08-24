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
const { recordAuditLog } = await import("@/lib/db/auditLog");
const { GET: getAudit } = await import("../route");

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("GET /api/admin/audit", () => {
  it("401s with no session", async () => {
    expect((await getAudit(new Request("http://localhost/api/admin/audit"))).status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = await createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    expect((await getAudit(new Request("http://localhost/api/admin/audit"))).status).toBe(403);
  });

  it("lists audit entries, filterable by search", async () => {
    const admin = await createUser({ email: "admin@example.com", passwordHash: "h" });
    await updateUserRole(admin.id, "ADMIN");
    await establishSession(admin.id, null);
    await recordAuditLog({ actorUserId: admin.id, actorLabel: admin.email, action: "user_role_changed", targetType: "user", targetId: "x" });
    await recordAuditLog({ actorUserId: admin.id, actorLabel: admin.email, action: "sport_status_changed", targetType: "sport", targetId: "NFL" });

    const res = await getAudit(new Request("http://localhost/api/admin/audit?search=sport_status"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.entries).toHaveLength(1);
    expect(body.entries[0].action).toBe("sport_status_changed");
  });
});
