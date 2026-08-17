import { getBillingMode } from "@/lib/billing/stripeConfig";

/** Server component -- renders nothing outside stripe_test mode. Never
 * indicates "live" (that mode is refused at the code level, not just
 * hidden here -- see lib/billing/stripeConfig.ts). */
export function StripeTestModeBadge() {
  if (getBillingMode() !== "stripe_test") return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-yellow/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-yellow">
      ⚠ Stripe Test Mode
    </span>
  );
}
