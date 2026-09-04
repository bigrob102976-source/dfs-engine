import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getTodayEasternDate } from "@/lib/currentDate";
import { getExternalProjectionsStatus } from "@/lib/externalProjectionsStatus";

export const dynamic = "force-dynamic";

/** External projection provider / baseline / adjusted status for
 * today's slate -- backs the (Milestone 29: admin-only) Settings page.
 * See lib/externalProjectionsStatus.ts -- both this route and the
 * server-rendered Settings page share the same underlying call so
 * provider resolution only ever happens in Python. Never returns an API
 * key. */
export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = getTodayEasternDate();
  const status = await getExternalProjectionsStatus(date);
  if ("error" in status) {
    return NextResponse.json(status, { status: 502 });
  }
  return NextResponse.json(status);
}
