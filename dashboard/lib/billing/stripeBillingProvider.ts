import { getPlan } from "@/lib/db/plans";
import { findSubscriptionByProviderSubscriptionId, getSubscriptionById, updateSubscriptionStatus } from "@/lib/db/subscriptions";
import type { Subscription } from "@/lib/db/types";
import { findUserById, setStripeCustomerId } from "@/lib/db/users";

import { getStripeClient } from "./stripeClient";
import { getStripeEnvConfig } from "./stripeConfig";
import type { BillingProvider, CheckoutResult, PortalResult } from "./types";
import { applyStripeSubscription } from "./webhookHandlers";

/** Server-side allowlist mapping ("weekly"|"monthly" -> a configured
 * Stripe Price ID) -- the browser can never supply a raw Stripe Price ID
 * that ends up used in a real charge. */
function priceIdForPlan(planId: string): string | null {
  const config = getStripeEnvConfig();
  if (planId === "weekly") return config.weeklyPriceId;
  if (planId === "monthly") return config.monthlyPriceId;
  return null;
}

/**
 * Real Stripe billing (test mode only -- see lib/billing/stripeConfig.ts's
 * live-key guardrail, enforced upstream in lib/billing/index.ts before
 * this class is ever instantiated). Checkout and the Customer Portal are
 * both server-created, hosted, redirect-based flows -- no Stripe.js /
 * Elements / card data ever touches this server or its client.
 */
export class StripeBillingProvider implements BillingProvider {
  async createCheckoutSession(args: { userId: string; planId: string; origin: string }): Promise<CheckoutResult> {
    const plan = await getPlan(args.planId);
    if (!plan || plan.is_active !== 1) {
      return { error: `Unknown plan: ${args.planId}` };
    }
    const priceId = priceIdForPlan(args.planId);
    if (!priceId) {
      return { error: `No Stripe price configured for plan: ${args.planId}` };
    }
    const user = await findUserById(args.userId);
    if (!user) {
      return { error: "Unknown user." };
    }

    const stripe = getStripeClient();

    let customerId = user.stripe_customer_id;
    if (!customerId) {
      const customer = await stripe.customers.create({
        email: user.email,
        metadata: { bigmoney_user_id: user.id },
      });
      customerId = customer.id;
      await setStripeCustomerId(user.id, customerId);
    }

    const trialEligible = user.trial_consumed_at === null;

    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer: customerId,
      client_reference_id: user.id,
      line_items: [{ price: priceId, quantity: 1 }],
      subscription_data: {
        metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: args.planId },
        ...(trialEligible ? { trial_period_days: plan.trial_days } : {}),
      },
      metadata: { bigmoney_user_id: user.id, bigmoney_plan_id: args.planId },
      success_url: `${args.origin}/subscribe/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${args.origin}/subscribe/canceled`,
    });

    if (!session.url) {
      return { error: "Stripe did not return a Checkout URL." };
    }
    return { url: session.url };
  }

  async createCustomerPortalSession(args: { userId: string; origin: string }): Promise<PortalResult> {
    const user = await findUserById(args.userId);
    if (!user?.stripe_customer_id) {
      return { error: "No billing account on file yet -- start a subscription first." };
    }
    const stripe = getStripeClient();
    const session = await stripe.billingPortal.sessions.create({
      customer: user.stripe_customer_id,
      return_url: `${args.origin}/account/billing`,
    });
    return { url: session.url };
  }

  async cancelSubscription(subscriptionId: string): Promise<void> {
    const local = await getSubscriptionById(subscriptionId);
    if (!local || local.provider !== "stripe" || !local.provider_subscription_id) {
      throw new Error("Not a Stripe-backed subscription.");
    }
    const stripe = getStripeClient();
    await stripe.subscriptions.update(local.provider_subscription_id, { cancel_at_period_end: true });
    // Reflect immediately; the subsequent customer.subscription.updated
    // webhook will also confirm this through the canonical writer.
    await updateSubscriptionStatus(local.id, local.status, { cancel_at_period_end: 1 });
  }

  async syncSubscription(providerSubscriptionId: string): Promise<Subscription | null> {
    const stripe = getStripeClient();
    const subscription = await stripe.subscriptions.retrieve(providerSubscriptionId);
    const result = await applyStripeSubscription(subscription, new Date().toISOString());
    if (!result.ok) return null;
    return findSubscriptionByProviderSubscriptionId(subscription.id);
  }
}
