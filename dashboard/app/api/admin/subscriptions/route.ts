import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { listSubscriptions } from "@/lib/db/subscriptions";
import type { SubscriptionStatus } from "@/lib/db/types";

export const dynamic = "force-dynamic";

const VALID_STATUSES: SubscriptionStatus[] = ["trialing", "active", "past_due", "canceled", "expired", "complimentary"];

export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const url = new URL(request.url);
  const statusParam = url.searchParams.get("status");
  const status = statusParam && (VALID_STATUSES as string[]).includes(statusParam) ? (statusParam as SubscriptionStatus) : null;

  const subscriptions = listSubscriptions({
    status,
    planId: url.searchParams.get("planId"),
    search: url.searchParams.get("search"),
  });

  return NextResponse.json({ subscriptions });
}
