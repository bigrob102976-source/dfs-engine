import type Stripe from "stripe";

import type { SubscriptionStatus } from "@/lib/db/types";

/** The complete, documented mapping from every Stripe subscription
 * status to Big Money DFS's own SubscriptionStatus. Not invented ad hoc
 * -- this is the full set of values Stripe.Subscription.Status can hold
 * (confirmed against the installed `stripe` SDK's own type declarations):
 *
 *   trialing            -> trialing
 *   active               -> active
 *   past_due            -> past_due
 *   unpaid              -> past_due   (still recoverable via Stripe's retry/dunning; same "no access" outcome as past_due today)
 *   canceled            -> canceled
 *   incomplete          -> past_due   (first payment/3DS never completed -- never was active; maps to the same "no access" bucket)
 *   incomplete_expired  -> expired    (incomplete and the window to complete it has closed)
 *   paused              -> past_due   (rare; Stripe's own pause-collection feature isn't used by this app's Checkout flow, mapped defensively)
 *
 * Any value outside that set (Stripe's SDK types this as `OtherString`,
 * its own forward-compatibility escape hatch for statuses added after
 * this SDK version was released) maps to `past_due` -- a safe default
 * that grants no product access rather than guessing "active". */
export function mapStripeSubscriptionStatus(stripeStatus: Stripe.Subscription.Status): SubscriptionStatus {
  switch (stripeStatus) {
    case "trialing":
      return "trialing";
    case "active":
      return "active";
    case "past_due":
    case "unpaid":
    case "incomplete":
    case "paused":
      return "past_due";
    case "canceled":
      return "canceled";
    case "incomplete_expired":
      return "expired";
    default:
      return "past_due";
  }
}
