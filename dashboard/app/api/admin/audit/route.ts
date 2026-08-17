import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { listAuditLog } from "@/lib/db/auditLog";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const url = new URL(request.url);
  const entries = listAuditLog({
    action: url.searchParams.get("action"),
    search: url.searchParams.get("search"),
  });

  return NextResponse.json({ entries });
}
