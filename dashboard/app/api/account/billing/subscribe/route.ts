import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { getBillingProvider } from "@/lib/billing";
import { getPlan } from "@/lib/db/plans";
import { recordUsageEvent } from "@/lib/db/usageEvents";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const { planId } = (body ?? {}) as { planId?: unknown };
  if (typeof planId !== "string" || !getPlan(planId)) {
    return NextResponse.json({ error: "Unknown plan." }, { status: 400 });
  }

  const subscription = await getBillingProvider().createSubscription({ userId: user.id, planId });
  recordUsageEvent({ userId: user.id, eventType: "subscription_started", metadata: { planId } });
  return NextResponse.json({ ok: true, subscription });
}
