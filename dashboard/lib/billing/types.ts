import type { Subscription } from "@/lib/db/types";

/** Behind-an-interface billing, so a real payment processor (Stripe,
 * etc.) can be connected in a dedicated future billing milestone by
 * adding one new implementation file and changing index.ts's single
 * export -- nothing else in the app talks to a payment provider
 * directly, and no implementation of this interface may ever accept,
 * store, or log a card number, CVV, or other raw payment credential. */
export interface BillingProvider {
  createSubscription(args: { userId: string; planId: string }): Promise<Subscription>;
  cancelSubscription(subscriptionId: string): Promise<void>;
  /** null when the provider has no hosted management portal (true of
   * the dev provider; a real Stripe integration would return a Billing
   * Portal URL here). */
  getPortalUrl(userId: string): Promise<string | null>;
}
