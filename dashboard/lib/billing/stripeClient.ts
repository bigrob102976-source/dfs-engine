import Stripe from "stripe";

import { getStripeEnvConfig } from "./stripeConfig";

let stripeClient: Stripe | null = null;

/** Lazy singleton -- constructed on first real use, not at module load,
 * so importing this file never throws in a process where Stripe isn't
 * configured. Shared by StripeBillingProvider (checkout/portal/cancel/
 * sync) and the webhook route's invoice.paid/invoice.payment_failed
 * handlers (which need to retrieve a Subscription, not just verify a
 * signature). No apiVersion is pinned explicitly: the installed SDK's
 * own bundled default is used, which is the recommended approach for a
 * new integration. Only call this once getStripeConfigStatus().configured
 * is true. */
export function getStripeClient(): Stripe {
  if (!stripeClient) {
    stripeClient = new Stripe(getStripeEnvConfig().secretKey);
  }
  return stripeClient;
}

/** Signature verification uses Stripe's STATIC webhooks helper (does not
 * require an API key at all, only the webhook signing secret) -- kept
 * separate from getStripeClient() so the webhook route's signature check
 * never depends on STRIPE_SECRET_KEY being configured. */
export const stripeWebhooks = Stripe.webhooks;
