import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockCustomersCreate = vi.fn();
const mockCheckoutSessionsCreate = vi.fn();
const mockBillingPortalSessionsCreate = vi.fn();
const mockSubscriptionsUpdate = vi.fn();
const mockSubscriptionsRetrieve = vi.fn();

vi.mock("stripe", () => {
  class MockStripe {
    customers = { create: mockCustomersCreate };
    checkout = { sessions: { create: mockCheckoutSessionsCreate } };
    billingPortal = { sessions: { create: mockBillingPortalSessionsCreate } };
    subscriptions = { update: mockSubscriptionsUpdate, retrieve: mockSubscriptionsRetrieve };
  }
  return { default: MockStripe };
});

const TEST_ORIGIN = "https://bigmoneydfs.example";

function stubStripeEnv() {
  vi.stubEnv("STRIPE_SECRET_KEY", "sk_test_abc123");
  vi.stubEnv("STRIPE_WEBHOOK_SECRET", "whsec_abc123");
  vi.stubEnv("STRIPE_WEEKLY_PRICE_ID", "price_weekly_test");
  vi.stubEnv("STRIPE_MONTHLY_PRICE_ID", "price_monthly_test");
}

const { __resetDbForTests } = await import("@/lib/db/client");
const { createUser, findUserById, markTrialConsumed } = await import("@/lib/db/users");
const { insertSubscription, getSubscriptionById, findSubscriptionByProviderSubscriptionId } = await import("@/lib/db/subscriptions");
const { StripeBillingProvider } = await import("../stripeBillingProvider");

beforeEach(() => {
  __resetDbForTests();
  stubStripeEnv();
  mockCustomersCreate.mockReset();
  mockCheckoutSessionsCreate.mockReset();
  mockBillingPortalSessionsCreate.mockReset();
  mockSubscriptionsUpdate.mockReset();
  mockSubscriptionsRetrieve.mockReset();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("StripeBillingProvider.createCheckoutSession", () => {
  it("creates a NEW Stripe customer for a user with none yet, and persists the id", async () => {
    mockCustomersCreate.mockResolvedValue({ id: "cus_new123" });
    mockCheckoutSessionsCreate.mockResolvedValue({ url: "https://checkout.stripe.com/session/abc" });

    const provider = new StripeBillingProvider();
    const user = createUser({ email: "newcustomer@example.com", passwordHash: "h" });

    const result = await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });

    expect(result).toEqual({ url: "https://checkout.stripe.com/session/abc" });
    expect(mockCustomersCreate).toHaveBeenCalledWith({ email: "newcustomer@example.com", metadata: { bigmoney_user_id: user.id } });
    expect(findUserById(user.id)?.stripe_customer_id).toBe("cus_new123");
  });

  it("REUSES an existing Stripe customer id instead of creating a new one", async () => {
    mockCheckoutSessionsCreate.mockResolvedValue({ url: "https://checkout.stripe.com/session/xyz" });
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "existingcustomer@example.com", passwordHash: "h" });
    const { setStripeCustomerId } = await import("@/lib/db/users");
    setStripeCustomerId(user.id, "cus_existing456");

    await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });

    expect(mockCustomersCreate).not.toHaveBeenCalled();
    expect(mockCheckoutSessionsCreate).toHaveBeenCalledWith(expect.objectContaining({ customer: "cus_existing456" }));
  });

  it("maps 'weekly'/'monthly' to the CONFIGURED Stripe price id -- never a browser-supplied one", async () => {
    mockCustomersCreate.mockResolvedValue({ id: "cus_1" });
    mockCheckoutSessionsCreate.mockResolvedValue({ url: "https://checkout.stripe.com/x" });
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "pricecheck@example.com", passwordHash: "h" });

    // Simulates an attacker trying to smuggle an arbitrary price id in --
    // the interface only accepts a plan id string, so there is no field
    // for a raw price id to even flow through in the first place.
    await provider.createCheckoutSession({
      userId: user.id,
      planId: "weekly",
      origin: TEST_ORIGIN,
      // @ts-expect-error -- intentionally testing that extra fields are ignored
      priceId: "price_attacker_supplied",
    });

    expect(mockCheckoutSessionsCreate).toHaveBeenCalledWith(
      expect.objectContaining({ line_items: [{ price: "price_weekly_test", quantity: 1 }] }),
    );
  });

  it("includes trial_period_days for a trial-eligible user", async () => {
    mockCustomersCreate.mockResolvedValue({ id: "cus_1" });
    mockCheckoutSessionsCreate.mockResolvedValue({ url: "https://checkout.stripe.com/x" });
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "trialok@example.com", passwordHash: "h" });

    await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });

    const call = mockCheckoutSessionsCreate.mock.calls[0][0];
    expect(call.subscription_data.trial_period_days).toBe(3);
  });

  it("omits trial_period_days for a user who already consumed their trial", async () => {
    mockCustomersCreate.mockResolvedValue({ id: "cus_1" });
    mockCheckoutSessionsCreate.mockResolvedValue({ url: "https://checkout.stripe.com/x" });
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "trialused@example.com", passwordHash: "h" });
    markTrialConsumed(user.id);

    await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });

    const call = mockCheckoutSessionsCreate.mock.calls[0][0];
    expect(call.subscription_data.trial_period_days).toBeUndefined();
  });

  it("sets client_reference_id and subscription_data.metadata from the AUTHENTICATED user, never client input", async () => {
    mockCustomersCreate.mockResolvedValue({ id: "cus_1" });
    mockCheckoutSessionsCreate.mockResolvedValue({ url: "https://checkout.stripe.com/x" });
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "identitycheck@example.com", passwordHash: "h" });

    await provider.createCheckoutSession({ userId: user.id, planId: "monthly", origin: TEST_ORIGIN });

    const call = mockCheckoutSessionsCreate.mock.calls[0][0];
    expect(call.client_reference_id).toBe(user.id);
    expect(call.subscription_data.metadata).toEqual({ bigmoney_user_id: user.id, bigmoney_plan_id: "monthly" });
  });

  it("builds success/cancel URLs from the server-supplied origin, not any user-suppliable value", async () => {
    mockCustomersCreate.mockResolvedValue({ id: "cus_1" });
    mockCheckoutSessionsCreate.mockResolvedValue({ url: "https://checkout.stripe.com/x" });
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "urlcheck@example.com", passwordHash: "h" });

    await provider.createCheckoutSession({ userId: user.id, planId: "weekly", origin: TEST_ORIGIN });

    const call = mockCheckoutSessionsCreate.mock.calls[0][0];
    expect(call.success_url).toBe(`${TEST_ORIGIN}/subscribe/success?session_id={CHECKOUT_SESSION_ID}`);
    expect(call.cancel_url).toBe(`${TEST_ORIGIN}/subscribe/canceled`);
  });

  it("returns an error for an unknown plan id (never calls Stripe)", async () => {
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "badplan2@example.com", passwordHash: "h" });
    const result = await provider.createCheckoutSession({ userId: user.id, planId: "yearly", origin: TEST_ORIGIN });
    expect(result).toHaveProperty("error");
    expect(mockCheckoutSessionsCreate).not.toHaveBeenCalled();
  });

  it("returns an error for an unknown user id", async () => {
    const provider = new StripeBillingProvider();
    const result = await provider.createCheckoutSession({ userId: "no-such-user", planId: "weekly", origin: TEST_ORIGIN });
    expect(result).toHaveProperty("error");
  });
});

describe("StripeBillingProvider.createCustomerPortalSession", () => {
  it("returns an error when the user has no Stripe customer on file", async () => {
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "noportal@example.com", passwordHash: "h" });
    const result = await provider.createCustomerPortalSession({ userId: user.id, origin: TEST_ORIGIN });
    expect(result).toHaveProperty("error");
    expect(mockBillingPortalSessionsCreate).not.toHaveBeenCalled();
  });

  it("creates a portal session for a customer with a stripe_customer_id, using the server-side return_url", async () => {
    mockBillingPortalSessionsCreate.mockResolvedValue({ url: "https://billing.stripe.com/session/portal1" });
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "hasportal@example.com", passwordHash: "h" });
    const { setStripeCustomerId } = await import("@/lib/db/users");
    setStripeCustomerId(user.id, "cus_portalcheck");

    const result = await provider.createCustomerPortalSession({ userId: user.id, origin: TEST_ORIGIN });

    expect(result).toEqual({ url: "https://billing.stripe.com/session/portal1" });
    expect(mockBillingPortalSessionsCreate).toHaveBeenCalledWith({
      customer: "cus_portalcheck",
      return_url: `${TEST_ORIGIN}/account/billing`,
    });
  });
});

describe("StripeBillingProvider.cancelSubscription", () => {
  it("sets cancel_at_period_end on Stripe AND reflects it locally right away", async () => {
    mockSubscriptionsUpdate.mockResolvedValue({});
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "cancelstripe@example.com", passwordHash: "h" });
    const sub = insertSubscription({
      userId: user.id,
      planId: "weekly",
      status: "active",
      provider: "stripe",
      providerSubscriptionId: "sub_cancelme",
    });

    await provider.cancelSubscription(sub.id);

    expect(mockSubscriptionsUpdate).toHaveBeenCalledWith("sub_cancelme", { cancel_at_period_end: true });
    expect(getSubscriptionById(sub.id)?.cancel_at_period_end).toBe(1);
  });

  it("refuses to act on a non-Stripe (dev-provider) subscription", async () => {
    const provider = new StripeBillingProvider();
    const user = createUser({ email: "notstripe@example.com", passwordHash: "h" });
    const sub = insertSubscription({ userId: user.id, planId: "weekly", status: "active" }); // provider defaults to 'dev'

    await expect(provider.cancelSubscription(sub.id)).rejects.toThrow();
    expect(mockSubscriptionsUpdate).not.toHaveBeenCalled();
  });
});

describe("StripeBillingProvider.syncSubscription", () => {
  it("retrieves the subscription from Stripe and reconciles it locally via the canonical writer", async () => {
    const user = createUser({ email: "syncme@example.com", passwordHash: "h" });
    mockSubscriptionsRetrieve.mockResolvedValue({
      id: "sub_syncme",
      status: "active",
      customer: "cus_x",
      metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: "weekly" },
      trial_end: null,
      cancel_at_period_end: false,
      canceled_at: null,
      items: { data: [{ current_period_start: 1755000000, current_period_end: 1755600000, price: { id: "price_weekly_test" } }] },
    });

    const provider = new StripeBillingProvider();
    const result = await provider.syncSubscription("sub_syncme");

    expect(mockSubscriptionsRetrieve).toHaveBeenCalledWith("sub_syncme");
    expect(result?.status).toBe("active");
    expect(findSubscriptionByProviderSubscriptionId("sub_syncme")).not.toBeNull();
  });
});
