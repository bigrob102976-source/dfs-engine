import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { getBillingProvider } from "@/lib/billing";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const origin = new URL(request.url).origin;
  const result = await getBillingProvider().createCustomerPortalSession({ userId: user.id, origin });

  if (result === null) {
    return NextResponse.json({ error: "No billing portal available in development mode." }, { status: 501 });
  }
  if ("error" in result) {
    return NextResponse.json({ error: result.error }, { status: 502 });
  }
  return NextResponse.json({ url: result.url });
}
