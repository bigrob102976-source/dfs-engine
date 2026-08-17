import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type Stripe from "stripe";

import { __resetDbForTests } from "@/lib/db/client";
import { listAuditLog } from "@/lib/db/auditLog";
import { findSubscriptionByProviderSubscriptionId, getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";
import { createUser, findUserById, setStripeCustomerId } from "@/lib/db/users";

import {
  applyStripeSubscription,
  handleCheckoutSessionCompleted,
  handleInvoicePaid,
  handleInvoicePaymentFailed,
} from "../webhookHandlers";

const EVENT_TIME = "2026-08-17T12:00:00.000Z";

function fakeSubscription(overrides: Partial<Stripe.Subscription> = {}, itemOverrides: Record<string, unknown> = {}): Stripe.Subscription {
  return {
    id: "sub_test123",
    object: "subscription",
    status: "trialing",
    customer: "cus_test123",
    metadata: {},
    trial_end: null,
    cancel_at_period_end: false,
    canceled_at: null,
    items: {
      object: "list",
      data: [
        {
          id: "si_test123",
          object: "subscription_item",
          current_period_start: 1755432000, // 2025-08-17T08:00:00Z-ish, fixed test value
          current_period_end: 1756036800,
          price: { id: "price_weekly_test", object: "price" },
          ...itemOverrides,
        },
      ],
      has_more: false,
      url: "",
    },
    ...overrides,
  } as unknown as Stripe.Subscription;
}

function fakeCheckoutSession(overrides: Partial<Stripe.Checkout.Session> = {}): Stripe.Checkout.Session {
  return {
    id: "cs_test123",
    object: "checkout.session",
    client_reference_id: null,
    customer: "cus_test123",
    metadata: {},
    ...overrides,
  } as unknown as Stripe.Checkout.Session;
}

function fakeInvoice(overrides: Partial<Stripe.Invoice> = {}): Stripe.Invoice {
  return {
    id: "in_test123",
    object: "invoice",
    parent: { subscription_details: { subscription: "sub_test123", metadata: null }, quote_details: null, type: "subscription_details" },
    ...overrides,
  } as unknown as Stripe.Invoice;
}

beforeEach(() => {
  __resetDbForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("applyStripeSubscription", () => {
  it("returns unknown_user when neither metadata nor stripe_customer_id resolves a local user", () => {
    const result = applyStripeSubscription(fakeSubscription({ customer: "cus_nobody" }), EVENT_TIME);
    expect(result).toEqual({ ok: false, reason: "unknown_user" });
  });

  it("resolves the user via metadata.bigmoney_user_id when present", () => {
    const user = createUser({ email: "meta-user@example.com", passwordHash: "h" });
    const result = applyStripeSubscription(
      fakeSubscription({ metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" } }),
      EVENT_TIME,
    );
    expect(result.ok).toBe(true);
    expect(getCurrentSubscriptionForUser(user.id)?.user_id).toBe(user.id);
  });

  it("falls back to resolving the user via stripe_customer_id when metadata is absent", () => {
    const user = createUser({ email: "cus-fallback@example.com", passwordHash: "h" });
    setStripeCustomerId(user.id, "cus_fallback123");
    const result = applyStripeSubscription(
      fakeSubscription({ customer: "cus_fallback123", metadata: { bigmoney_plan_id: "monthly" } }),
      EVENT_TIME,
    );
    expect(result.ok).toBe(true);
    expect(getCurrentSubscriptionForUser(user.id)?.plan_id).toBe("monthly");
  });

  it("returns unknown_plan when metadata is missing/invalid and no price-ID fallback is configured", () => {
    const user = createUser({ email: "noplan@example.com", passwordHash: "h" });
    const result = applyStripeSubscription(fakeSubscription({ metadata: { bigmoney_user_id: user.id } }), EVENT_TIME);
    expect(result).toEqual({ ok: false, reason: "unknown_plan" });
  });

  it("resolves the plan via reverse price-ID lookup when Stripe is configured and metadata is missing (defensive fallback)", () => {
    vi.stubEnv("STRIPE_SECRET_KEY", "sk_test_abc");
    vi.stubEnv("STRIPE_WEBHOOK_SECRET", "whsec_abc");
    vi.stubEnv("STRIPE_WEEKLY_PRICE_ID", "price_weekly_test");
    vi.stubEnv("STRIPE_MONTHLY_PRICE_ID", "price_monthly_test");

    const user = createUser({ email: "pricefallback@example.com", passwordHash: "h" });
    const result = applyStripeSubscription(
      fakeSubscription({ metadata: { bigmoney_user_id: user.id } }, { price: { id: "price_weekly_test" } }),
      EVENT_TIME,
    );
    expect(result.ok).toBe(true);
    expect(getCurrentSubscriptionForUser(user.id)?.plan_id).toBe("weekly");
  });

  it("inserts a new stripe-provider subscription row with every field mapped correctly", () => {
    const user = createUser({ email: "insertnew@example.com", passwordHash: "h" });
    const trialEndUnix = Math.floor(Date.parse("2026-08-20T00:00:00Z") / 1000);
    applyStripeSubscription(
      fakeSubscription({
        id: "sub_new123",
        status: "trialing",
        trial_end: trialEndUnix,
        cancel_at_period_end: false,
        metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" },
      }),
      EVENT_TIME,
    );

    const sub = getCurrentSubscriptionForUser(user.id)!;
    expect(sub.provider).toBe("stripe");
    expect(sub.provider_subscription_id).toBe("sub_new123");
    expect(sub.provider_price_id).toBe("price_weekly_test");
    expect(sub.status).toBe("trialing");
    expect(sub.trial_ends_at).toBe("2026-08-20T00:00:00.000Z");
    expect(sub.cancel_at_period_end).toBe(0);
    expect(sub.last_stripe_event_at).toBe(EVENT_TIME);
  });

  it("marks the user's trial consumed when trial_end is present, and NOT when absent", () => {
    const trialUser = createUser({ email: "trialconsumed@example.com", passwordHash: "h" });
    applyStripeSubscription(
      fakeSubscription({
        id: "sub_trial1",
        trial_end: Math.floor(Date.now() / 1000) + 86400,
        metadata: { bigmoney_user_id: trialUser.id, bigmoney_plan_id: "weekly" },
      }),
      EVENT_TIME,
    );
    expect(findUserById(trialUser.id)?.trial_consumed_at).not.toBeNull();

    const noTrialUser = createUser({ email: "notrial@example.com", passwordHash: "h" });
    applyStripeSubscription(
      fakeSubscription({
        id: "sub_notrial1",
        status: "active",
        trial_end: null,
        metadata: { bigmoney_user_id: noTrialUser.id, bigmoney_plan_id: "weekly" },
      }),
      EVENT_TIME,
    );
    expect(findUserById(noTrialUser.id)?.trial_consumed_at).toBeNull();
  });

  it("updates an existing local row (found by provider_subscription_id) rather than inserting a duplicate", () => {
    const user = createUser({ email: "updateexisting@example.com", passwordHash: "h" });
    applyStripeSubscription(
      fakeSubscription({ id: "sub_update1", status: "trialing", metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" } }),
      "2026-08-17T12:00:00.000Z",
    );
    applyStripeSubscription(
      fakeSubscription({
        id: "sub_update1",
        status: "active",
        cancel_at_period_end: true,
        metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" },
      }),
      "2026-08-17T12:05:00.000Z",
    );

    const sub = findSubscriptionByProviderSubscriptionId("sub_update1")!;
    expect(sub.status).toBe("active");
    expect(sub.cancel_at_period_end).toBe(1);
    // Still exactly one row for this Stripe subscription -- no duplicate insert.
    expect(getCurrentSubscriptionForUser(user.id)?.id).toBe(sub.id);
  });

  it("skips (no-op) an event older than the last one already applied -- out-of-order delivery guard", () => {
    const user = createUser({ email: "staleorder@example.com", passwordHash: "h" });
    applyStripeSubscription(
      fakeSubscription({ id: "sub_stale1", status: "active", metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" } }),
      "2026-08-17T12:10:00.000Z",
    );
    // A delayed/retried event, timestamped BEFORE the one already applied.
    const result = applyStripeSubscription(
      fakeSubscription({
        id: "sub_stale1",
        status: "past_due", // would regress status if wrongly applied
        metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" },
      }),
      "2026-08-17T12:00:00.000Z",
    );
    expect(result).toEqual({ ok: true, reason: "stale_event_skipped" });
    expect(findSubscriptionByProviderSubscriptionId("sub_stale1")?.status).toBe("active");
  });

  it("records a subscription_synchronized audit entry with no secrets, only identifiers/status", () => {
    const user = createUser({ email: "auditcheck@example.com", passwordHash: "h" });
    applyStripeSubscription(
      fakeSubscription({ id: "sub_audit1", status: "active", metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" } }),
      EVENT_TIME,
    );
    const entries = listAuditLog({ action: "subscription_synchronized" });
    expect(entries).toHaveLength(1);
    expect(entries[0].actor_label).toBe("stripe_webhook");
    expect(entries[0].metadata_json).toContain("sub_audit1");
    expect(entries[0].metadata_json).not.toMatch(/sk_test|whsec_/);
  });
});

describe("handleCheckoutSessionCompleted", () => {
  it("maps the stripe customer id onto the user when both are resolvable", () => {
    const user = createUser({ email: "checkoutmap@example.com", passwordHash: "h" });
    const result = handleCheckoutSessionCompleted(
      fakeCheckoutSession({ client_reference_id: user.id, customer: "cus_mapped123" }),
    );
    expect(result.ok).toBe(true);
    expect(findUserById(user.id)?.stripe_customer_id).toBe("cus_mapped123");
  });

  it("does not overwrite an already-set stripe_customer_id", () => {
    const user = createUser({ email: "alreadymapped@example.com", passwordHash: "h" });
    setStripeCustomerId(user.id, "cus_original");
    handleCheckoutSessionCompleted(fakeCheckoutSession({ client_reference_id: user.id, customer: "cus_different" }));
    expect(findUserById(user.id)?.stripe_customer_id).toBe("cus_original");
  });

  it("returns ok:false when the user cannot be resolved", () => {
    const result = handleCheckoutSessionCompleted(fakeCheckoutSession({ client_reference_id: null, metadata: {} }));
    expect(result.ok).toBe(false);
  });

  it("records a checkout_completed audit entry", () => {
    const user = createUser({ email: "checkoutaudit@example.com", passwordHash: "h" });
    handleCheckoutSessionCompleted(fakeCheckoutSession({ client_reference_id: user.id, customer: "cus_auditcheck" }));
    expect(listAuditLog({ action: "checkout_completed" })).toHaveLength(1);
  });
});

describe("handleInvoicePaid / handleInvoicePaymentFailed", () => {
  it("re-fetches and syncs the associated subscription via the canonical writer", async () => {
    const user = createUser({ email: "invoicepaid@example.com", passwordHash: "h" });
    const fetchSubscription = vi.fn().mockResolvedValue(
      fakeSubscription({ id: "sub_invoice1", status: "active", metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" } }),
    );

    const result = await handleInvoicePaid(
      fakeInvoice({ parent: { subscription_details: { subscription: "sub_invoice1", metadata: null }, quote_details: null, type: "subscription_details" } }),
      EVENT_TIME,
      fetchSubscription,
    );

    expect(result.ok).toBe(true);
    expect(fetchSubscription).toHaveBeenCalledWith("sub_invoice1");
    expect(getCurrentSubscriptionForUser(user.id)?.status).toBe("active");
  });

  it("handles an expanded (object, not string) subscription reference on the invoice", async () => {
    const user = createUser({ email: "expandedref@example.com", passwordHash: "h" });
    const fetchSubscription = vi.fn().mockResolvedValue(
      fakeSubscription({ id: "sub_expanded1", status: "past_due", metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" } }),
    );
    const invoice = fakeInvoice({
      parent: {
        subscription_details: { subscription: { id: "sub_expanded1" } as Stripe.Subscription, metadata: null },
        quote_details: null,
        type: "subscription_details",
      },
    });

    await handleInvoicePaymentFailed(invoice, EVENT_TIME, fetchSubscription);
    expect(fetchSubscription).toHaveBeenCalledWith("sub_expanded1");
  });

  it("returns ok:false without calling fetchSubscription when the invoice has no subscription reference", async () => {
    const fetchSubscription = vi.fn();
    const result = await handleInvoicePaid(fakeInvoice({ parent: null }), EVENT_TIME, fetchSubscription);
    expect(result).toEqual({ ok: false, reason: "no_subscription_on_invoice" });
    expect(fetchSubscription).not.toHaveBeenCalled();
  });
});
