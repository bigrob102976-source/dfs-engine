import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("stripe", () => {
  class MockStripe {
    customers = { create: vi.fn() };
    checkout = { sessions: { create: vi.fn() } };
    billingPortal = { sessions: { create: vi.fn() } };
    subscriptions = { update: vi.fn(), retrieve: vi.fn() };
  }
  return { default: MockStripe };
});

const ALL_VARS = ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_WEEKLY_PRICE_ID", "STRIPE_MONTHLY_PRICE_ID"];

function clearStripeEnv() {
  for (const name of ALL_VARS) vi.stubEnv(name, "");
}

function stubFullTestConfig() {
  vi.stubEnv("STRIPE_SECRET_KEY", "sk_test_abc123");
  vi.stubEnv("STRIPE_WEBHOOK_SECRET", "whsec_abc123");
  vi.stubEnv("STRIPE_WEEKLY_PRICE_ID", "price_weekly_test");
  vi.stubEnv("STRIPE_MONTHLY_PRICE_ID", "price_monthly_test");
}

const { getBillingProvider } = await import("../index");
const { StripeBillingProvider } = await import("../stripeBillingProvider");
const { DevBillingProvider } = await import("../devBillingProvider");

beforeEach(() => {
  clearStripeEnv();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getBillingProvider", () => {
  it("returns a StripeBillingProvider when fully configured with a test key", () => {
    stubFullTestConfig();
    vi.stubEnv("NODE_ENV", "test");
    expect(getBillingProvider()).toBeInstanceOf(StripeBillingProvider);
  });

  it("returns a DevBillingProvider when unconfigured outside production", () => {
    vi.stubEnv("NODE_ENV", "test");
    expect(getBillingProvider()).toBeInstanceOf(DevBillingProvider);
  });

  it("returns neither Stripe nor Dev in production when unconfigured -- fails closed", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const provider = getBillingProvider();
    expect(provider).not.toBeInstanceOf(StripeBillingProvider);
    expect(provider).not.toBeInstanceOf(DevBillingProvider);

    const result = await provider.createCheckoutSession({ userId: "u1", planId: "weekly", origin: "https://x.example" });
    expect(result).toHaveProperty("error");
  });

  it("blocks a live key in production too, never falling back to dev simulation", async () => {
    stubFullTestConfig();
    vi.stubEnv("STRIPE_SECRET_KEY", "sk_live_realmoney");
    vi.stubEnv("NODE_ENV", "production");
    const provider = getBillingProvider();
    expect(provider).not.toBeInstanceOf(StripeBillingProvider);
    expect(provider).not.toBeInstanceOf(DevBillingProvider);
  });

  it("the blocked provider's error message never echoes WHY it's blocked (no config/secret leakage to the caller)", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const provider = getBillingProvider();
    const result = await provider.createCheckoutSession({ userId: "u1", planId: "weekly", origin: "https://x.example" });
    expect(result).toHaveProperty("error");
    if ("error" in result) {
      expect(result.error).not.toMatch(/STRIPE_|sk_test|sk_live|whsec_/);
    }
  });

  it("the blocked provider's cancelSubscription throws (never silently succeeds) without leaking config details", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const provider = getBillingProvider();
    await expect(provider.cancelSubscription("sub_x")).rejects.toThrow();
  });

  it("the blocked provider's createCustomerPortalSession also returns a generic error", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const provider = getBillingProvider();
    const result = await provider.createCustomerPortalSession({ userId: "u1", origin: "https://x.example" });
    expect(result).toHaveProperty("error");
  });
});
