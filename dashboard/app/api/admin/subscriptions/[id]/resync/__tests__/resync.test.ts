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

const mockSyncSubscription = vi.fn();
vi.mock("@/lib/billing", () => ({
  getBillingProvider: () => ({ syncSubscription: mockSyncSubscription }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser, updateUserRole } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { insertSubscription } = await import("@/lib/db/subscriptions");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { POST: resync } = await import("../route");

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
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
  mockSyncSubscription.mockReset();
});

describe("POST /api/admin/subscriptions/[id]/resync", () => {
  it("401s with no session", async () => {
    const res = await resync(new Request("http://localhost/x", { method: "POST" }), ctx("x"));
    expect(res.status).toBe(401);
  });

  it("403s for a MEMBER", async () => {
    const member = await createUser({ email: "member@example.com", passwordHash: "h" });
    await establishSession(member.id, null);
    const res = await resync(new Request("http://localhost/x", { method: "POST" }), ctx("x"));
    expect(res.status).toBe(403);
  });

  it("404s for an unknown subscription id", async () => {
    await loginAsAdmin();
    const res = await resync(new Request("http://localhost/x", { method: "POST" }), ctx("no-such-sub"));
    expect(res.status).toBe(404);
  });

  it("400s for a non-Stripe (dev-provider) subscription -- never fabricates a Stripe sync for it", async () => {
    await loginAsAdmin();
    const user = await createUser({ email: "devsub@example.com", passwordHash: "h" });
    const sub = await insertSubscription({ userId: user.id, planId: "weekly", status: "active" }); // provider='dev'

    const res = await resync(new Request("http://localhost/x", { method: "POST" }), ctx(sub.id));
    expect(res.status).toBe(400);
    expect(mockSyncSubscription).not.toHaveBeenCalled();
  });

  it("resyncs a Stripe-backed subscription and writes an audit log entry", async () => {
    const admin = await loginAsAdmin();
    const user = await createUser({ email: "stripesub@example.com", passwordHash: "h" });
    const sub = await insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "past_due",
      provider: "stripe",
      providerSubscriptionId: "sub_resync1",
    });
    mockSyncSubscription.mockResolvedValue({ ...sub, status: "active" });

    const res = await resync(new Request("http://localhost/x", { method: "POST" }), ctx(sub.id));
    expect(res.status).toBe(200);
    expect(mockSyncSubscription).toHaveBeenCalledWith("sub_resync1");

    const entries = await listAuditLog({ action: "admin_subscription_resync" });
    expect(entries).toHaveLength(1);
    expect(entries[0].actor_user_id).toBe(admin.id);
    expect(entries[0].target_id).toBe(sub.id);
  });

  it("502s when the provider fails to resync (never fabricates a result)", async () => {
    await loginAsAdmin();
    const user = await createUser({ email: "syncfail@example.com", passwordHash: "h" });
    const sub = await insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "active",
      provider: "stripe",
      providerSubscriptionId: "sub_fail1",
    });
    mockSyncSubscription.mockResolvedValue(null);

    const res = await resync(new Request("http://localhost/x", { method: "POST" }), ctx(sub.id));
    expect(res.status).toBe(502);
    expect(await listAuditLog({ action: "admin_subscription_resync" })).toHaveLength(0);
  });
});
