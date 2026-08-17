import type { Subscription } from "@/lib/db/types";

export type CheckoutResult = { url: string } | { error: string };
export type PortalResult = { url: string } | { error: string } | null;

/** Behind-an-interface billing so DevBillingProvider (local simulation)
 * and StripeBillingProvider (real, test-mode-only Stripe) are fully
 * interchangeable -- nothing else in the app talks to a payment
 * provider directly, and no implementation of this interface may ever
 * accept, store, or log a card number, CVV, or other raw payment
 * credential. Both Checkout and the Customer Portal are hosted,
 * redirect-based flows (the caller does `window.location.href = url`),
 * never an embedded card form. */
export interface BillingProvider {
  /** Starts a subscription flow for planId ("weekly"|"monthly"). Returns
   * a URL to redirect the browser to (a real Stripe Checkout page, or
   * DevBillingProvider's own internal /subscribe/success for local
   * simulation) -- never completes the subscription synchronously,
   * since a real payment flow requires the browser to leave the app. */
  /** origin is the caller's own request origin (e.g. `new URL(request.url).origin`
   * from the API route) -- used to build success/cancel/return URLs
   * server-side. Never derived from user-suppliable redirect params, so
   * this introduces no open-redirect surface. */
  createCheckoutSession(args: { userId: string; planId: string; origin: string }): Promise<CheckoutResult>;
  /** null when the provider has no hosted management portal (true of
   * the dev provider). */
  createCustomerPortalSession(args: { userId: string; origin: string }): Promise<PortalResult>;
  /** Cancel-at-period-end where the provider supports it (Stripe); an
   * immediate local cancel for the dev provider. */
  cancelSubscription(subscriptionId: string): Promise<void>;
  /** Re-fetch the provider's authoritative state for a subscription (by
   * its provider_subscription_id) and reconcile the local row. Used by
   * the webhook handler's defensive re-sync path and the admin "Resync
   * from Stripe" action; a pure local read for the dev provider (which
   * has no external state to reconcile against). */
  syncSubscription(providerSubscriptionId: string): Promise<Subscription | null>;
}
