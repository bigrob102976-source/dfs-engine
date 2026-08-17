import { getPlan } from "@/lib/db/plans";
import { cancelSubscription as cancelSubscriptionRow, insertSubscription } from "@/lib/db/subscriptions";
import type { Subscription } from "@/lib/db/types";

import type { BillingProvider } from "./types";

/**
 * DEV-ONLY billing provider -- NOT a real payment integration.
 *
 * No payment processor (Stripe or otherwise) is configured anywhere in
 * this project (confirmed: no `stripe` dependency, no payment-provider
 * environment variables). Per this milestone's explicit "IMPORTANT
 * BILLING LIMIT," real charges are never activated here -- this
 * provider only simulates a trial subscription starting locally:
 * - Never collects, stores, or transmits a card number, CVV, or any
 *   other raw payment credential.
 * - Never contacts any external payment network.
 * - Always starts the subscription in `trialing` status for the plan's
 *   configured trial_days -- there is no "immediately active, real
 *   charge" path in this adapter.
 *
 * Connecting a real processor (Stripe) is a deferred, dedicated future
 * billing milestone -- swap the single export in lib/billing/index.ts
 * for a real implementation of BillingProvider; nothing else in the
 * app needs to change.
 */
export class DevBillingProvider implements BillingProvider {
  async createSubscription(args: { userId: string; planId: string }): Promise<Subscription> {
    const plan = getPlan(args.planId);
    if (!plan) {
      throw new Error(`Unknown plan: ${args.planId}`);
    }
    const trialEndsAt = new Date(Date.now() + plan.trial_days * 24 * 60 * 60 * 1000).toISOString();
    return insertSubscription({
      userId: args.userId,
      planId: plan.id,
      status: "trialing",
      trialEndsAt,
      currentPeriodEnd: trialEndsAt,
    });
  }

  async cancelSubscription(subscriptionId: string): Promise<void> {
    cancelSubscriptionRow(subscriptionId);
  }

  async getPortalUrl(): Promise<string | null> {
    return null;
  }
}
