import type { Subscription } from "@/lib/db/types";

import { DevBillingProvider } from "./devBillingProvider";
import { getStripeConfigStatus } from "./stripeConfig";
import { StripeBillingProvider } from "./stripeBillingProvider";
import type { BillingProvider, CheckoutResult, PortalResult } from "./types";

export type { BillingProvider } from "./types";

const GENERIC_USER_MESSAGE = "Billing is not available right now. Please try again later.";

/** Every method logs the REAL reason server-side (config missing / live
 * key blocked) but only ever returns a generic message to the caller --
 * never leaks which env vars are missing or that a live key was
 * rejected to an end user. Used when Stripe isn't configured AND we're
 * in production, so the app fails closed instead of silently falling
 * back to DevBillingProvider's local simulation. */
class BlockedBillingProvider implements BillingProvider {
  constructor(private readonly reason: string) {}

  private logBlocked(method: string): void {
    console.error(`[billing] ${method} blocked: ${this.reason}`);
  }

  async createCheckoutSession(): Promise<CheckoutResult> {
    this.logBlocked("createCheckoutSession");
    return { error: GENERIC_USER_MESSAGE };
  }

  async createCustomerPortalSession(): Promise<PortalResult> {
    this.logBlocked("createCustomerPortalSession");
    return { error: GENERIC_USER_MESSAGE };
  }

  async cancelSubscription(): Promise<void> {
    this.logBlocked("cancelSubscription");
    throw new Error(GENERIC_USER_MESSAGE);
  }

  async syncSubscription(): Promise<Subscription | null> {
    this.logBlocked("syncSubscription");
    return null;
  }
}

let stripeProvider: StripeBillingProvider | null = null;
let devProvider: DevBillingProvider | null = null;

/** Provider selection (documented, see dashboard/STRIPE_TESTING.md):
 *   1. Stripe fully configured with a TEST key -> StripeBillingProvider.
 *   2. Otherwise, outside production -> DevBillingProvider (preserves
 *      the pre-Stripe local-dev experience, always clearly labeled in
 *      the UI via getBillingMode()).
 *   3. Otherwise (production, Stripe missing/misconfigured/live-key-
 *      blocked) -> BlockedBillingProvider. Production NEVER silently
 *      falls back to the dev simulation. */
export function getBillingProvider(): BillingProvider {
  const status = getStripeConfigStatus();

  if (status.configured) {
    if (!stripeProvider) stripeProvider = new StripeBillingProvider();
    return stripeProvider;
  }

  if (process.env.NODE_ENV !== "production") {
    if (!devProvider) devProvider = new DevBillingProvider();
    return devProvider;
  }

  const reason = status.blocked ? status.reason : `Stripe is not configured (missing: ${status.missing.join(", ")}).`;
  return new BlockedBillingProvider(reason);
}
