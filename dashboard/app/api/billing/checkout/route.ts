import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { getBillingProvider } from "@/lib/billing";
import { recordAuditLog } from "@/lib/db/auditLog";
import { getPlan } from "@/lib/db/plans";

export const dynamic = "force-dynamic";

/** The browser sends only an internal plan identifier ("weekly"/
 * "monthly", validated against the plans catalog) -- never a raw Stripe
 * Price ID. The provider maps that identifier to the configured price
 * server-side (see StripeBillingProvider.priceIdForPlan). userId is
 * always the session-authenticated user, never client-suppliable. */
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
  if (typeof planId !== "string" || !(await getPlan(planId))) {
    return NextResponse.json({ error: "Unknown plan." }, { status: 400 });
  }

  const origin = new URL(request.url).origin;
  const result = await getBillingProvider().createCheckoutSession({ userId: user.id, planId, origin });

  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: 502 });
  }

  await recordAuditLog({
    actorUserId: user.id,
    actorLabel: user.email,
    action: "checkout_initiated",
    targetType: "user",
    targetId: user.id,
    metadata: { planId },
  });

  return NextResponse.json({ url: result.url });
}
