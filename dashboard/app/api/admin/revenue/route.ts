import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { computeAdminRevenueStats } from "@/lib/admin/revenueStats";

export const dynamic = "force-dynamic";

export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  return NextResponse.json(computeAdminRevenueStats());
}
