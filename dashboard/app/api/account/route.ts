import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { getPlan } from "@/lib/db/plans";
import { listSports } from "@/lib/db/sports";
import { getCurrentSubscriptionForUser } from "@/lib/db/subscriptions";
import { computeUserAccess } from "@/lib/entitlements/computeAccess";

export const dynamic = "force-dynamic";

export async function GET() {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const subscription = getCurrentSubscriptionForUser(user.id);
  const plan = subscription ? getPlan(subscription.plan_id) : null;
  const access = computeUserAccess(user);

  return NextResponse.json({
    email: user.email,
    role: user.role,
    displayName: user.displayName,
    subscription: subscription
      ? {
          status: subscription.status,
          planName: plan?.name ?? null,
          trialEndsAt: subscription.trial_ends_at,
          currentPeriodEnd: subscription.current_period_end,
        }
      : null,
    entitlementCount: access.entitlementKeys.size,
    sports: listSports(),
  });
}
