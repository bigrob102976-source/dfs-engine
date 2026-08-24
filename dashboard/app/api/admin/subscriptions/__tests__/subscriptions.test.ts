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
const { insertSubscription } = await import("@/lib/db/subscriptions");
const { GET: listSubscriptions } = await import("../route");

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
});

describe("GET /api/admin/subscriptions", () => {
  it("401s with no session", async () => {
    const res = await listSubscriptions(new Request("http://localhost/api/admin/subscriptions"));
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = await createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await listSubscriptions(new Request("http://localhost/api/admin/subscriptions"));
    expect(res.status).toBe(403);
  });

  it("lists subscriptions for an ADMIN, filtered by status", async () => {
    const admin = await createUser({ email: "admin@example.com", passwordHash: "h" });
    await updateUserRole(admin.id, "ADMIN");
    await establishSession(admin.id, null);

    const active = await createUser({ email: "active@example.com", passwordHash: "h" });
    await insertSubscription({ userId: active.id, planId: "weekly", status: "active" });
    const trialing = await createUser({ email: "trialing@example.com", passwordHash: "h" });
    await insertSubscription({ userId: trialing.id, planId: "monthly", status: "trialing" });

    const res = await listSubscriptions(new Request("http://localhost/api/admin/subscriptions?status=active"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.subscriptions).toHaveLength(1);
    expect(body.subscriptions[0].user_email).toBe("active@example.com");
  });

  it("ignores an invalid status value rather than erroring", async () => {
    const admin = await createUser({ email: "admin2@example.com", passwordHash: "h" });
    await updateUserRole(admin.id, "ADMIN");
    await establishSession(admin.id, null);

    const res = await listSubscriptions(new Request("http://localhost/api/admin/subscriptions?status=not-a-status"));
    expect(res.status).toBe(200);
  });
});
