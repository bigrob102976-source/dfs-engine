import type Stripe from "stripe";

import { recordAuditLog } from "@/lib/db/auditLog";
import {
  findSubscriptionByProviderSubscriptionId,
  insertSubscription,
  updateSubscriptionStatus,
} from "@/lib/db/subscriptions";
import { findUserById, findUserByStripeCustomerId, markTrialConsumed, setStripeCustomerId } from "@/lib/db/users";

import { getStripeConfigStatus, getStripeEnvConfig } from "./stripeConfig";
import { mapStripeSubscriptionStatus } from "./stripeStatusMapping";

export interface HandlerResult {
  ok: boolean;
  reason?: string;
}

function unixToIso(unixSeconds: number | null | undefined): string | null {
  return typeof unixSeconds === "number" ? new Date(unixSeconds * 1000).toISOString() : null;
}

function stripeCustomerId(customer: Stripe.Subscription["customer"] | Stripe.Checkout.Session["customer"]): string | null {
  if (!customer) return null;
  return typeof customer === "string" ? customer : customer.id;
}

async function resolveUserId(subscription: Stripe.Subscription): Promise<string | null> {
  const metaUserId = subscription.metadata?.bigmoney_user_id;
  if (metaUserId) return metaUserId;
  const customerId = stripeCustomerId(subscription.customer);
  if (!customerId) return null;
  return (await findUserByStripeCustomerId(customerId))?.id ?? null;
}

/** Primary source: the plan id set as Checkout Session metadata when we
 * created the subscription (see StripeBillingProvider.createCheckoutSession).
 * Fallback (defensive only -- e.g. a subscription created directly in the
 * Stripe Dashboard, bypassing our Checkout flow): reverse-lookup the
 * subscribed price ID against the two configured plan price IDs. */
function resolvePlanId(subscription: Stripe.Subscription): string | null {
  const metaPlanId = subscription.metadata?.bigmoney_plan_id;
  if (metaPlanId === "weekly" || metaPlanId === "monthly") return metaPlanId;

  const priceId = subscription.items.data[0]?.price?.id ?? null;
  if (!priceId) return null;
  const status = getStripeConfigStatus();
  if (!status.configured) return null;
  const config = getStripeEnvConfig();
  if (priceId === config.weeklyPriceId) return "weekly";
  if (priceId === config.monthlyPriceId) return "monthly";
  return null;
}

/** The SINGLE canonical writer of local subscription state from Stripe.
 * Used directly for customer.subscription.created/updated/deleted (all
 * three carry a full Subscription object and are handled identically --
 * a "deleted" subscription simply arrives with status='canceled'
 * already set by Stripe), and indirectly by handleInvoicePaid/
 * handleInvoicePaymentFailed's defensive re-sync, and by
 * StripeBillingProvider.syncSubscription's on-demand resync.
 *
 * Always applies the FULL authoritative state from the Stripe object
 * (never an incremental delta), which is what makes webhook
 * reprocessing safe under lib/db/stripeWebhookEvents.ts's claim logic.
 *
 * Out-of-order guard: Stripe does not guarantee webhook delivery order.
 * eventCreatedIso is compared against the local row's last_stripe_event_at
 * (both are fixed-width ISO-8601 UTC strings, so lexicographic comparison
 * is a valid chronological comparison) -- a delayed/retried older event
 * arriving after a newer one was already applied is a documented no-op,
 * not an error. */
export async function applyStripeSubscription(subscription: Stripe.Subscription, eventCreatedIso: string): Promise<HandlerResult> {
  const userId = await resolveUserId(subscription);
  if (!userId) return { ok: false, reason: "unknown_user" };

  const planId = resolvePlanId(subscription);
  if (!planId) return { ok: false, reason: "unknown_plan" };

  const item = subscription.items.data[0];
  const status = mapStripeSubscriptionStatus(subscription.status);
  const trialEndsAt = unixToIso(subscription.trial_end);
  const currentPeriodStart = unixToIso(item?.current_period_start ?? null);
  const currentPeriodEnd = unixToIso(item?.current_period_end ?? null);
  const canceledAt = unixToIso(subscription.canceled_at);
  const providerPriceId = item?.price?.id ?? null;

  const existing = await findSubscriptionByProviderSubscriptionId(subscription.id);

  if (existing) {
    if (existing.last_stripe_event_at && eventCreatedIso < existing.last_stripe_event_at) {
      return { ok: true, reason: "stale_event_skipped" };
    }
    await updateSubscriptionStatus(existing.id, status, {
      current_period_start: currentPeriodStart,
      current_period_end: currentPeriodEnd,
      cancel_at_period_end: subscription.cancel_at_period_end ? 1 : 0,
      canceled_at: canceledAt,
      provider_price_id: providerPriceId,
      last_stripe_event_at: eventCreatedIso,
    });
  } else {
    await insertSubscription({
      userId,
      planId,
      status,
      provider: "stripe",
      providerSubscriptionId: subscription.id,
      providerPriceId,
      trialEndsAt,
      currentPeriodStart,
      currentPeriodEnd,
      cancelAtPeriodEnd: subscription.cancel_at_period_end,
      lastStripeEventAt: eventCreatedIso,
    });
  }

  // One-trial policy: consumption is confirmed by Stripe actually
  // granting a trial (trial_end present), never by mere checkout-session
  // creation -- idempotent, safe to call on every sync.
  if (trialEndsAt) await markTrialConsumed(userId);

  await recordAuditLog({
    actorUserId: null,
    actorLabel: "stripe_webhook",
    action: "subscription_synchronized",
    targetType: "user",
    targetId: userId,
    metadata: { stripeSubscriptionId: subscription.id, status, planId },
  });

  return { ok: true };
}

/** checkout.session.completed only maps the Stripe Customer ID and
 * audit-logs -- it deliberately never writes subscription status, since
 * Stripe does not guarantee this event arrives before
 * customer.subscription.created (see applyStripeSubscription's doc
 * comment for the canonical writer). */
export async function handleCheckoutSessionCompleted(session: Stripe.Checkout.Session): Promise<HandlerResult> {
  const userId = session.client_reference_id ?? session.metadata?.bigmoney_user_id ?? null;
  const customerId = stripeCustomerId(session.customer);

  if (userId && customerId) {
    const user = await findUserById(userId);
    if (user && !user.stripe_customer_id) {
      await setStripeCustomerId(userId, customerId);
    }
  }

  await recordAuditLog({
    actorUserId: userId,
    actorLabel: userId ? "member" : "stripe_webhook",
    action: "checkout_completed",
    targetType: "user",
    targetId: userId,
    metadata: { stripeCheckoutSessionId: session.id, stripeCustomerId: customerId },
  });

  if (!userId || !customerId) return { ok: false, reason: "missing_user_or_customer" };
  return { ok: true };
}

function resolveInvoiceSubscriptionId(invoice: Stripe.Invoice): string | null {
  const ref = invoice.parent?.subscription_details?.subscription;
  if (!ref) return null;
  return typeof ref === "string" ? ref : ref.id;
}

/** invoice.paid/invoice.payment_failed are handled identically: re-fetch
 * and re-sync the associated subscription through the same canonical
 * writer rather than trusting the invoice event's own embedded status --
 * customer.subscription.updated should already have fired for the same
 * transition, so this is a redundant safety net, not the primary
 * mechanism. fetchSubscription is injected (rather than importing a
 * Stripe client directly) so this stays unit-testable without mocking
 * the whole SDK. */
async function syncInvoiceSubscription(
  invoice: Stripe.Invoice,
  eventCreatedIso: string,
  fetchSubscription: (id: string) => Promise<Stripe.Subscription>,
): Promise<HandlerResult> {
  const subscriptionId = resolveInvoiceSubscriptionId(invoice);
  if (!subscriptionId) return { ok: false, reason: "no_subscription_on_invoice" };
  const subscription = await fetchSubscription(subscriptionId);
  return applyStripeSubscription(subscription, eventCreatedIso);
}

export async function handleInvoicePaid(
  invoice: Stripe.Invoice,
  eventCreatedIso: string,
  fetchSubscription: (id: string) => Promise<Stripe.Subscription>,
): Promise<HandlerResult> {
  return syncInvoiceSubscription(invoice, eventCreatedIso, fetchSubscription);
}

export async function handleInvoicePaymentFailed(
  invoice: Stripe.Invoice,
  eventCreatedIso: string,
  fetchSubscription: (id: string) => Promise<Stripe.Subscription>,
): Promise<HandlerResult> {
  return syncInvoiceSubscription(invoice, eventCreatedIso, fetchSubscription);
}
