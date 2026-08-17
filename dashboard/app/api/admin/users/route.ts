import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { countAdminUsers, listAdminUsers } from "@/lib/db/adminUsers";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const url = new URL(request.url);
  const filter = {
    search: url.searchParams.get("search"),
    role: url.searchParams.get("role"),
    planId: url.searchParams.get("planId"),
    subscriptionStatus: url.searchParams.get("subscriptionStatus"),
    trialStatus: url.searchParams.get("trialStatus"),
  };

  return NextResponse.json({
    users: listAdminUsers(filter),
    total: countAdminUsers(filter),
  });
}
