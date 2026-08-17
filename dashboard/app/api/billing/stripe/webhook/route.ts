import { NextResponse } from "next/server";
import type Stripe from "stripe";

import { claimWebhookEvent, markWebhookEventFailed, markWebhookEventProcessed } from "@/lib/db/stripeWebhookEvents";
import { getStripeClient, stripeWebhooks } from "@/lib/billing/stripeClient";
import { getStripeConfigStatus, getStripeEnvConfig } from "@/lib/billing/stripeConfig";
import {
  applyStripeSubscription,
  handleCheckoutSessionCompleted,
  handleInvoicePaid,
  handleInvoicePaymentFailed,
} from "@/lib/billing/webhookHandlers";

export const dynamic = "force-dynamic";

/** Stripe's webhook endpoint. Deliberately NOT wrapped in
 * requireAuthApi()/requireAdminApi() -- Stripe's requests carry no
 * session cookie at all; the stripe-signature check below is the entire
 * auth story for this route (see proxy.ts's PUBLIC_PATH_PREFIXES, which
 * exempts this exact path from the session-cookie redirect gate).
 *
 * Reads the RAW request body via request.text() (never request.json()
 * first) -- Stripe's signature is computed over the exact bytes it sent,
 * and this app has no middleware that would consume/alter the body
 * before this handler runs. */
export async function POST(request: Request) {
  const configStatus = getStripeConfigStatus();
  if (!configStatus.configured) {
    console.error("[stripe-webhook] Received a webhook while Stripe is not configured or blocked -- rejecting.");
    return NextResponse.json({ error: "Webhook not configured." }, { status: 500 });
  }

  const signature = request.headers.get("stripe-signature");
  if (!signature) {
    return NextResponse.json({ error: "Missing stripe-signature header." }, { status: 400 });
  }

  const rawBody = await request.text();
  const { webhookSecret } = getStripeEnvConfig();

  let event: Stripe.Event;
  try {
    event = stripeWebhooks.constructEvent(rawBody, signature, webhookSecret);
  } catch (err) {
    console.error(`[stripe-webhook] Signature verification failed: ${err instanceof Error ? err.message : String(err)}`);
    return NextResponse.json({ error: "Invalid signature." }, { status: 400 });
  }

  // Idempotency: an event already fully processed is a true duplicate
  // delivery -- no-op, still 200 (never re-triggers Stripe's retry
  // backoff for something already handled).
  const { shouldProcess } = claimWebhookEvent(event.id, event.type);
  if (!shouldProcess) {
    return NextResponse.json({ ok: true, deduped: true });
  }

  const eventCreatedIso = new Date(event.created * 1000).toISOString();
  const fetchSubscription = (id: string) => getStripeClient().subscriptions.retrieve(id);

  try {
    switch (event.type) {
      case "checkout.session.completed":
        handleCheckoutSessionCompleted(event.data.object as Stripe.Checkout.Session);
        break;
      // All three subscription lifecycle events carry a full Subscription
      // object and are handled identically through the same canonical
      // writer -- a "deleted" subscription simply arrives with
      // status='canceled' already set by Stripe.
      case "customer.subscription.created":
      case "customer.subscription.updated":
      case "customer.subscription.deleted":
        applyStripeSubscription(event.data.object as Stripe.Subscription, eventCreatedIso);
        break;
      case "invoice.paid":
        await handleInvoicePaid(event.data.object as Stripe.Invoice, eventCreatedIso, fetchSubscription);
        break;
      case "invoice.payment_failed":
        await handleInvoicePaymentFailed(event.data.object as Stripe.Invoice, eventCreatedIso, fetchSubscription);
        break;
      default:
        // An event type we don't act on -- not an error, just nothing to do.
        break;
    }
    markWebhookEventProcessed(event.id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[stripe-webhook] Handler failed for ${event.type} (${event.id}): ${message}`);
    markWebhookEventFailed(event.id, message);
    // Non-2xx so Stripe's own retry/backoff schedule retries this event later.
    return NextResponse.json({ error: "Webhook handler failed." }, { status: 500 });
  }
}
