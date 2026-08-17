import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { getBillingProvider } from "@/lib/billing";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";
import { recordUsageEvent } from "@/lib/db/usageEvents";

export const dynamic = "force-dynamic";

export async function POST() {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const subscription = getCurrentSubscriptionForUser(user.id);
  if (!subscription || subscription.status === "canceled") {
    return NextResponse.json({ error: "No active subscription to cancel." }, { status: 400 });
  }

  await getBillingProvider().cancelSubscription(subscription.id);
  recordUsageEvent({ userId: user.id, eventType: "subscription_canceled" });
  return NextResponse.json({ ok: true });
}
