import { getPlan } from "@/lib/db/plans";
import {
  cancelSubscription as cancelSubscriptionRow,
  findSubscriptionByProviderSubscriptionId,
  insertSubscription,
} from "@/lib/db/subscriptions";
import type { Subscription } from "@/lib/db/types";
import { findUserById, markTrialConsumed } from "@/lib/db/users";

import type { BillingProvider, CheckoutResult, PortalResult } from "./types";

const WEEKLY_INTERVAL_DAYS = 7;
const MONTHLY_INTERVAL_DAYS = 30;

/**
 * DEV-ONLY billing provider -- NOT a real payment integration. Used
 * automatically outside production when Stripe isn't configured (see
 * lib/billing/index.ts), and clearly labeled wherever it's active in
 * the UI.
 *
 * - Never collects, stores, or transmits a card number, CVV, or any
 *   other raw payment credential.
 * - Never contacts any external payment network.
 * - Respects the SAME one-trial-policy as StripeBillingProvider
 *   (users.trial_consumed_at is the single, provider-agnostic source of
 *   truth -- see lib/db/users.ts's markTrialConsumed) -- a user who has
 *   already consumed their trial gets an immediately-`active`
 *   subscription here too, not a second free trial.
 * - createCheckoutSession() mimics the real redirect-based contract
 *   (returns a URL) but completes synchronously and locally, so there
 *   is never an "immediately active, real charge" path here -- only
 *   `/subscribe/success`, the same page a real Stripe redirect lands on.
 */
export class DevBillingProvider implements BillingProvider {
  async createCheckoutSession(args: { userId: string; planId: string; origin: string }): Promise<CheckoutResult> {
    const plan = getPlan(args.planId);
    if (!plan || plan.is_active !== 1) {
      return { error: `Unknown plan: ${args.planId}` };
    }
    const user = findUserById(args.userId);
    if (!user) {
      return { error: "Unknown user." };
    }

    const trialEligible = user.trial_consumed_at === null;
    const intervalDays = plan.billing_interval === "WEEKLY" ? WEEKLY_INTERVAL_DAYS : MONTHLY_INTERVAL_DAYS;

    if (trialEligible) {
      const trialEndsAt = new Date(Date.now() + plan.trial_days * 24 * 60 * 60 * 1000).toISOString();
      insertSubscription({
        userId: args.userId,
        planId: plan.id,
        status: "trialing",
        trialEndsAt,
        currentPeriodEnd: trialEndsAt,
      });
      markTrialConsumed(args.userId);
    } else {
      const currentPeriodEnd = new Date(Date.now() + intervalDays * 24 * 60 * 60 * 1000).toISOString();
      insertSubscription({
        userId: args.userId,
        planId: plan.id,
        status: "active",
        currentPeriodEnd,
      });
    }

    return { url: "/subscribe/success" };
  }

  async createCustomerPortalSession(): Promise<PortalResult> {
    return null;
  }

  async cancelSubscription(subscriptionId: string): Promise<void> {
    cancelSubscriptionRow(subscriptionId);
  }

  async syncSubscription(providerSubscriptionId: string): Promise<Subscription | null> {
    // Dev-provider subscriptions have no external state to reconcile
    // against -- this is a pure local read for interface compatibility.
    return findSubscriptionByProviderSubscriptionId(providerSubscriptionId);
  }
}
