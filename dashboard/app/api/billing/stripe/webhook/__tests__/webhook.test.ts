import Stripe from "stripe";
import { beforeEach, describe, expect, it, vi } from "vitest";

const TEST_WEBHOOK_SECRET = "whsec_test_secret_for_route_tests";

const mockGetStripeConfigStatus = vi.fn();
const mockGetStripeEnvConfig = vi.fn();
vi.mock("@/lib/billing/stripeConfig", () => ({
  getStripeConfigStatus: () => mockGetStripeConfigStatus(),
  getStripeEnvConfig: () => mockGetStripeEnvConfig(),
}));

const mockApplyStripeSubscription = vi.fn();
const mockHandleCheckoutSessionCompleted = vi.fn();
const mockHandleInvoicePaid = vi.fn();
const mockHandleInvoicePaymentFailed = vi.fn();
vi.mock("@/lib/billing/webhookHandlers", () => ({
  applyStripeSubscription: (...args: unknown[]) => mockApplyStripeSubscription(...args),
  handleCheckoutSessionCompleted: (...args: unknown[]) => mockHandleCheckoutSessionCompleted(...args),
  handleInvoicePaid: (...args: unknown[]) => mockHandleInvoicePaid(...args),
  handleInvoicePaymentFailed: (...args: unknown[]) => mockHandleInvoicePaymentFailed(...args),
}));

const { __resetDbForTests } = await import("@/lib/db/client");
const { __resetExecutorForTests } = await import("@/lib/db/executor");
const { listRecentWebhookEvents } = await import("@/lib/db/stripeWebhookEvents");
const { POST: webhook } = await import("../route");

function signedRequest(payload: Record<string, unknown>, secret = TEST_WEBHOOK_SECRET): Request {
  const body = JSON.stringify(payload);
  const signature = Stripe.webhooks.generateTestHeaderString({ payload: body, secret });
  return new Request("http://localhost/api/billing/stripe/webhook", {
    method: "POST",
    headers: { "stripe-signature": signature, "content-type": "application/json" },
    body,
  });
}

function eventPayload(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    id: "evt_default",
    object: "event",
    type: "customer.subscription.updated",
    created: 1755432000,
    data: { object: { id: "sub_x", object: "subscription" } },
    ...overrides,
  };
}

beforeEach(() => {
  __resetDbForTests();
  __resetExecutorForTests();
  mockGetStripeConfigStatus.mockReturnValue({ configured: true, blocked: false });
  mockGetStripeEnvConfig.mockReturnValue({
    secretKey: "sk_test_x",
    publishableKey: null,
    webhookSecret: TEST_WEBHOOK_SECRET,
    weeklyPriceId: "price_weekly_test",
    monthlyPriceId: "price_monthly_test",
  });
  mockApplyStripeSubscription.mockReset().mockReturnValue({ ok: true });
  mockHandleCheckoutSessionCompleted.mockReset().mockReturnValue({ ok: true });
  mockHandleInvoicePaid.mockReset().mockResolvedValue({ ok: true });
  mockHandleInvoicePaymentFailed.mockReset().mockResolvedValue({ ok: true });
});

describe("POST /api/billing/stripe/webhook -- configuration and signature", () => {
  it("500s without touching the DB when Stripe is not configured", async () => {
    mockGetStripeConfigStatus.mockReturnValue({ configured: false, blocked: false, missing: ["STRIPE_WEBHOOK_SECRET"] });
    const res = await webhook(signedRequest(eventPayload({ id: "evt_unconfigured" })));
    expect(res.status).toBe(500);
    expect(await listRecentWebhookEvents()).toHaveLength(0);
  });

  it("400s when the stripe-signature header is missing", async () => {
    const res = await webhook(
      new Request("http://localhost/api/billing/stripe/webhook", { method: "POST", body: JSON.stringify(eventPayload({})) }),
    );
    expect(res.status).toBe(400);
  });

  it("400s on an invalid/forged signature and never calls a handler", async () => {
    const res = await webhook(signedRequest(eventPayload({ id: "evt_forged" }), "whsec_wrong_secret"));
    expect(res.status).toBe(400);
    expect(mockApplyStripeSubscription).not.toHaveBeenCalled();
    expect(await listRecentWebhookEvents()).toHaveLength(0);
  });

  it("accepts a validly-signed event and returns 200", async () => {
    const res = await webhook(signedRequest(eventPayload({ id: "evt_valid1" })));
    expect(res.status).toBe(200);
  });
});

describe("POST /api/billing/stripe/webhook -- dispatch to the correct handler", () => {
  it("customer.subscription.created/updated/deleted all dispatch to applyStripeSubscription", async () => {
    for (const type of ["customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"]) {
      mockApplyStripeSubscription.mockClear();
      await webhook(signedRequest(eventPayload({ id: `evt_${type}`, type })));
      expect(mockApplyStripeSubscription).toHaveBeenCalledTimes(1);
      expect(mockApplyStripeSubscription.mock.calls[0][0]).toMatchObject({ id: "sub_x" });
      expect(mockApplyStripeSubscription.mock.calls[0][1]).toBe(new Date(1755432000 * 1000).toISOString());
    }
  });

  it("checkout.session.completed dispatches to handleCheckoutSessionCompleted", async () => {
    await webhook(
      signedRequest(eventPayload({ id: "evt_checkout1", type: "checkout.session.completed", data: { object: { id: "cs_x" } } })),
    );
    expect(mockHandleCheckoutSessionCompleted).toHaveBeenCalledTimes(1);
    expect(mockHandleCheckoutSessionCompleted.mock.calls[0][0]).toMatchObject({ id: "cs_x" });
  });

  it("invoice.paid dispatches to handleInvoicePaid with a fetchSubscription callback", async () => {
    await webhook(signedRequest(eventPayload({ id: "evt_invoicepaid1", type: "invoice.paid", data: { object: { id: "in_x" } } })));
    expect(mockHandleInvoicePaid).toHaveBeenCalledTimes(1);
    const [invoiceArg, eventCreatedArg, fetchFn] = mockHandleInvoicePaid.mock.calls[0];
    expect(invoiceArg).toMatchObject({ id: "in_x" });
    expect(typeof eventCreatedArg).toBe("string");
    expect(typeof fetchFn).toBe("function");
  });

  it("invoice.payment_failed dispatches to handleInvoicePaymentFailed", async () => {
    await webhook(
      signedRequest(eventPayload({ id: "evt_invoicefail1", type: "invoice.payment_failed", data: { object: { id: "in_y" } } })),
    );
    expect(mockHandleInvoicePaymentFailed).toHaveBeenCalledTimes(1);
  });

  it("an unrecognized event type is a 200 no-op, not an error", async () => {
    const res = await webhook(signedRequest(eventPayload({ id: "evt_unknown1", type: "some.future.event" })));
    expect(res.status).toBe(200);
    expect(mockApplyStripeSubscription).not.toHaveBeenCalled();
    expect(mockHandleCheckoutSessionCompleted).not.toHaveBeenCalled();
  });
});

describe("POST /api/billing/stripe/webhook -- idempotency", () => {
  it("processes a duplicate delivery of the SAME event id only once", async () => {
    const payload = eventPayload({ id: "evt_duplicate1" });
    const first = await webhook(signedRequest(payload));
    expect(first.status).toBe(200);
    expect((await first.json()).deduped).toBeUndefined();

    const second = await webhook(signedRequest(payload));
    expect(second.status).toBe(200);
    expect((await second.json()).deduped).toBe(true);

    expect(mockApplyStripeSubscription).toHaveBeenCalledTimes(1);
  });

  it("retries an event whose PRIOR delivery failed (not permanently stuck)", async () => {
    mockApplyStripeSubscription.mockImplementationOnce(() => {
      throw new Error("boom");
    });
    const payload = eventPayload({ id: "evt_retry1" });

    const first = await webhook(signedRequest(payload));
    expect(first.status).toBe(500);

    const second = await webhook(signedRequest(payload));
    expect(second.status).toBe(200);
    expect(mockApplyStripeSubscription).toHaveBeenCalledTimes(2);

    const events = await listRecentWebhookEvents();
    expect(events.find((e) => e.id === "evt_retry1")?.status).toBe("processed");
  });
});

describe("POST /api/billing/stripe/webhook -- handler failure", () => {
  it("500s and records the failure without crashing when a handler throws", async () => {
    mockApplyStripeSubscription.mockImplementation(() => {
      throw new Error("db exploded");
    });
    const res = await webhook(signedRequest(eventPayload({ id: "evt_fail1" })));
    expect(res.status).toBe(500);

    const events = await listRecentWebhookEvents();
    const row = events.find((e) => e.id === "evt_fail1");
    expect(row?.status).toBe("failed");
    expect(row?.error).toContain("db exploded");
  });
});
