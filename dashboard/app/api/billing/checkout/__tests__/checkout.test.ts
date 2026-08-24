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

const mockCreateCheckoutSession = vi.fn();
vi.mock("@/lib/billing", () => ({
  getBillingProvider: () => ({ createCheckoutSession: mockCreateCheckoutSession }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { listAuditLog } = await import("@/lib/db/auditLog");
const { POST: checkout } = await import("../route");

function jsonRequest(url: string, body: unknown) {
  return new Request(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  cookieStore.clear();
  mockCreateCheckoutSession.mockReset();
});

describe("POST /api/billing/checkout", () => {
  it("401s with no session", async () => {
    const res = await checkout(jsonRequest("http://localhost/api/billing/checkout", { planId: "weekly" }));
    expect(res.status).toBe(401);
    expect(mockCreateCheckoutSession).not.toHaveBeenCalled();
  });

  it("400s for an unknown plan id", async () => {
    const user = await createUser({ email: "unknownplan@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const res = await checkout(jsonRequest("http://localhost/api/billing/checkout", { planId: "yearly" }));
    expect(res.status).toBe(400);
    expect(mockCreateCheckoutSession).not.toHaveBeenCalled();
  });

  it("400s for a malformed JSON body", async () => {
    const user = await createUser({ email: "malformed@example.com", passwordHash: "h" });
    await establishSession(user.id, null);
    const res = await checkout(
      new Request("http://localhost/api/billing/checkout", { method: "POST", headers: { "content-type": "application/json" }, body: "{not json" }),
    );
    expect(res.status).toBe(400);
  });

  it("creates a checkout session, using the SESSION user's id -- ignores any userId the body tries to supply", async () => {
    mockCreateCheckoutSession.mockResolvedValue({ url: "https://checkout.stripe.com/session/abc" });
    const user = await createUser({ email: "spoofcheck@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    const res = await checkout(
      jsonRequest("http://localhost/api/billing/checkout", { planId: "weekly", userId: "attacker-controlled-id" }),
    );
    expect(res.status).toBe(200);
    expect((await res.json()).url).toBe("https://checkout.stripe.com/session/abc");
    expect(mockCreateCheckoutSession).toHaveBeenCalledWith({ userId: user.id, planId: "weekly", origin: "http://localhost" });
  });

  it("ignores an arbitrary raw priceId the body tries to smuggle in -- only planId is ever read", async () => {
    mockCreateCheckoutSession.mockResolvedValue({ url: "https://checkout.stripe.com/session/xyz" });
    const user = await createUser({ email: "priceidcheck@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    await checkout(jsonRequest("http://localhost/api/billing/checkout", { planId: "monthly", priceId: "price_attacker_supplied" }));
    const call = mockCreateCheckoutSession.mock.calls[0][0];
    expect(call).not.toHaveProperty("priceId");
    expect(call.planId).toBe("monthly");
  });

  it("records a checkout_initiated audit log entry on success", async () => {
    mockCreateCheckoutSession.mockResolvedValue({ url: "https://checkout.stripe.com/session/abc" });
    const user = await createUser({ email: "auditcheckout@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    await checkout(jsonRequest("http://localhost/api/billing/checkout", { planId: "weekly" }));
    const entries = await listAuditLog({ action: "checkout_initiated" });
    expect(entries).toHaveLength(1);
    expect(entries[0].actor_user_id).toBe(user.id);
  });

  it("502s and does NOT audit-log when the provider returns an error", async () => {
    mockCreateCheckoutSession.mockResolvedValue({ error: "Stripe is down." });
    const user = await createUser({ email: "providererror@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    const res = await checkout(jsonRequest("http://localhost/api/billing/checkout", { planId: "weekly" }));
    expect(res.status).toBe(502);
    expect(await listAuditLog({ action: "checkout_initiated" })).toHaveLength(0);
  });
});
