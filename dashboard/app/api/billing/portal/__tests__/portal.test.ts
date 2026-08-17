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

const mockCreateCustomerPortalSession = vi.fn();
vi.mock("@/lib/billing", () => ({
  getBillingProvider: () => ({ createCustomerPortalSession: mockCreateCustomerPortalSession }),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser } = await import("@/lib/db/users");
const { establishSession } = await import("@/lib/auth/session");
const { POST: portal } = await import("../route");

function postRequest(url: string) {
  return new Request(url, { method: "POST" });
}

beforeEach(() => {
  __resetDbForTests();
  cookieStore.clear();
  mockCreateCustomerPortalSession.mockReset();
});

describe("POST /api/billing/portal", () => {
  it("401s with no session", async () => {
    const res = await portal(postRequest("http://localhost/api/billing/portal"));
    expect(res.status).toBe(401);
  });

  it("returns a portal URL for a subscribed user, using the session user's id and request origin", async () => {
    mockCreateCustomerPortalSession.mockResolvedValue({ url: "https://billing.stripe.com/session/portal1" });
    const user = createUser({ email: "portaluser@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    const res = await portal(postRequest("http://localhost/api/billing/portal"));
    expect(res.status).toBe(200);
    expect((await res.json()).url).toBe("https://billing.stripe.com/session/portal1");
    expect(mockCreateCustomerPortalSession).toHaveBeenCalledWith({ userId: user.id, origin: "http://localhost" });
  });

  it("501s when the provider has no hosted portal (dev mode)", async () => {
    mockCreateCustomerPortalSession.mockResolvedValue(null);
    const user = createUser({ email: "devmodeportal@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    const res = await portal(postRequest("http://localhost/api/billing/portal"));
    expect(res.status).toBe(501);
  });

  it("502s when the provider returns an error", async () => {
    mockCreateCustomerPortalSession.mockResolvedValue({ error: "No billing account on file yet." });
    const user = createUser({ email: "noaccount@example.com", passwordHash: "h" });
    await establishSession(user.id, null);

    const res = await portal(postRequest("http://localhost/api/billing/portal"));
    expect(res.status).toBe(502);
  });
});
