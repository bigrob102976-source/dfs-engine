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
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { getCurrentSubscriptionForUser } = await import("@/lib/db/subscriptions");
const { GET: getAccount } = await import("../route");
const { POST: subscribe } = await import("../billing/subscribe/route");
const { POST: cancel } = await import("../billing/cancel/route");

function jsonRequest(url: string, body: unknown) {
  return new Request(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
});

describe("GET /api/account", () => {
  it("401s with no session", async () => {
    const res = await getAccount();
    expect(res.status).toBe(401);
  });

  it("returns profile + null subscription + sports for a logged-in user with no subscription", async () => {
    const user = createUser({ email: "acct@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const res = await getAccount();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.email).toBe("acct@example.com");
    expect(body.role).toBe("MEMBER");
    expect(body.subscription).toBeNull();
    expect(body.sports.find((s: { code: string }) => s.code === "MLB").status).toBe("LIVE");
  });
});

describe("POST /api/account/billing/subscribe", () => {
  it("401s with no session", async () => {
    const res = await subscribe(jsonRequest("http://localhost/api/account/billing/subscribe", { planId: "weekly" }));
    expect(res.status).toBe(401);
  });

  it("400s for an unknown plan", async () => {
    const user = createUser({ email: "planless@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const res = await subscribe(jsonRequest("http://localhost/api/account/billing/subscribe", { planId: "nonexistent" }));
    expect(res.status).toBe(400);
  });

  it("creates a trialing subscription via the dev billing provider", async () => {
    const user = createUser({ email: "subscriber@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const res = await subscribe(jsonRequest("http://localhost/api/account/billing/subscribe", { planId: "weekly" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.subscription.status).toBe("trialing");
    expect(getCurrentSubscriptionForUser(user.id)?.status).toBe("trialing");
  });
});

describe("POST /api/account/billing/cancel", () => {
  it("401s with no session", async () => {
    const res = await cancel();
    expect(res.status).toBe(401);
  });

  it("400s when there is no subscription to cancel", async () => {
    const user = createUser({ email: "nosub@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const res = await cancel();
    expect(res.status).toBe(400);
  });

  it("cancels an active subscription", async () => {
    const user = createUser({ email: "cancelme@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    await subscribe(jsonRequest("http://localhost/api/account/billing/subscribe", { planId: "weekly" }));
    const res = await cancel();
    expect(res.status).toBe(200);
    expect(getCurrentSubscriptionForUser(user.id)?.status).toBe("canceled");
  });
});
