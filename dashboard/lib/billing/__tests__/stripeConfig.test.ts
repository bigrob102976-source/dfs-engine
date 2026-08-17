import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getBillingMode, getStripeConfigStatus, getStripeEnvConfig } from "../stripeConfig";

const ALL_VARS = ["STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_WEEKLY_PRICE_ID", "STRIPE_MONTHLY_PRICE_ID"];

function clearStripeEnv() {
  for (const name of ALL_VARS) vi.stubEnv(name, "");
}

function setFullTestConfig() {
  vi.stubEnv("STRIPE_SECRET_KEY", "sk_test_abc123");
  vi.stubEnv("STRIPE_PUBLISHABLE_KEY", "pk_test_abc123");
  vi.stubEnv("STRIPE_WEBHOOK_SECRET", "whsec_abc123");
  vi.stubEnv("STRIPE_WEEKLY_PRICE_ID", "price_weekly_test");
  vi.stubEnv("STRIPE_MONTHLY_PRICE_ID", "price_monthly_test");
}

beforeEach(() => {
  clearStripeEnv();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getStripeConfigStatus", () => {
  it("reports missing vars by name (never values) when nothing is configured", () => {
    const status = getStripeConfigStatus();
    expect(status.configured).toBe(false);
    if (!status.configured && !status.blocked) {
      expect(status.missing).toEqual(
        expect.arrayContaining(["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_WEEKLY_PRICE_ID", "STRIPE_MONTHLY_PRICE_ID"]),
      );
    } else {
      throw new Error("expected an unconfigured (not blocked) status");
    }
  });

  it("reports missing vars when only some are set", () => {
    vi.stubEnv("STRIPE_SECRET_KEY", "sk_test_abc123");
    const status = getStripeConfigStatus();
    expect(status.configured).toBe(false);
    if (!status.configured && !status.blocked) {
      expect(status.missing).not.toContain("STRIPE_SECRET_KEY");
      expect(status.missing).toContain("STRIPE_WEBHOOK_SECRET");
    }
  });

  it("is configured=true once all required vars are present with a test key", () => {
    setFullTestConfig();
    expect(getStripeConfigStatus()).toEqual({ configured: true, blocked: false });
  });

  it("STRIPE_PUBLISHABLE_KEY is NOT required (Checkout/Portal are redirect-based, no Stripe.js on the client)", () => {
    setFullTestConfig();
    vi.stubEnv("STRIPE_PUBLISHABLE_KEY", "");
    expect(getStripeConfigStatus().configured).toBe(true);
  });

  it("blocks a live secret key (sk_live_...) even when otherwise fully configured -- test mode only", () => {
    setFullTestConfig();
    vi.stubEnv("STRIPE_SECRET_KEY", "sk_live_realmoney");
    const status = getStripeConfigStatus();
    expect(status.configured).toBe(false);
    expect(status.blocked).toBe(true);
    if (status.blocked) {
      expect(status.reason).toMatch(/live key/i);
      expect(status.reason).not.toContain("sk_live_realmoney"); // never echoes the actual key value
    }
  });
});

describe("getBillingMode", () => {
  it("returns 'stripe_test' when fully configured with a test key", () => {
    setFullTestConfig();
    vi.stubEnv("NODE_ENV", "test");
    expect(getBillingMode()).toBe("stripe_test");
  });

  it("returns 'dev' when unconfigured outside production", () => {
    vi.stubEnv("NODE_ENV", "test");
    expect(getBillingMode()).toBe("dev");
  });

  it("returns 'unconfigured' (never 'dev') when unconfigured IN production -- fails closed", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(getBillingMode()).toBe("unconfigured");
  });

  it("returns 'unconfigured' in production even with a blocked live key", () => {
    setFullTestConfig();
    vi.stubEnv("STRIPE_SECRET_KEY", "sk_live_realmoney");
    vi.stubEnv("NODE_ENV", "production");
    expect(getBillingMode()).toBe("unconfigured");
  });
});

describe("getStripeEnvConfig", () => {
  it("returns every configured value", () => {
    setFullTestConfig();
    const config = getStripeEnvConfig();
    expect(config.secretKey).toBe("sk_test_abc123");
    expect(config.publishableKey).toBe("pk_test_abc123");
    expect(config.webhookSecret).toBe("whsec_abc123");
    expect(config.weeklyPriceId).toBe("price_weekly_test");
    expect(config.monthlyPriceId).toBe("price_monthly_test");
  });

  it("publishableKey is null when not set", () => {
    setFullTestConfig();
    vi.stubEnv("STRIPE_PUBLISHABLE_KEY", "");
    expect(getStripeEnvConfig().publishableKey).toBeNull();
  });
});
