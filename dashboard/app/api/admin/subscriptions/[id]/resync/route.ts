import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getBillingProvider } from "@/lib/billing";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getSubscriptionById } from "@/lib/db/subscriptions";

export const dynamic = "force-dynamic";

/** The only admin-side action that ever touches Stripe state, and it's
 * read-only from Stripe's perspective (re-fetches and reconciles, never
 * mutates). There is deliberately no database-only "cancel"/"activate"
 * admin action for Stripe-backed subscriptions -- that would leave the
 * real Stripe subscription running out of sync with a fabricated local
 * status. Complimentary access grants remain a separate, DB-only
 * concept untouched by this route. */
export async function POST(_request: Request, ctx: RouteContext<"/api/admin/subscriptions/[id]/resync">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const admin = userOrRes;

  const { id } = await ctx.params;
  const subscription = getSubscriptionById(id);
  if (!subscription) {
    return NextResponse.json({ error: "Subscription not found." }, { status: 404 });
  }
  if (subscription.provider !== "stripe" || !subscription.provider_subscription_id) {
    return NextResponse.json({ error: "Not a Stripe-backed subscription." }, { status: 400 });
  }

  const synced = await getBillingProvider().syncSubscription(subscription.provider_subscription_id);
  if (!synced) {
    return NextResponse.json({ error: "Failed to resync from Stripe." }, { status: 502 });
  }

  recordAuditLog({
    actorUserId: admin.id,
    actorLabel: admin.email,
    action: "admin_subscription_resync",
    targetType: "subscription",
    targetId: subscription.id,
    metadata: { stripeSubscriptionId: subscription.provider_subscription_id },
  });

  return NextResponse.json({ ok: true, subscription: synced });
}
