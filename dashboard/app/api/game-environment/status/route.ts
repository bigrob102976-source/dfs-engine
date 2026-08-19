import { NextResponse } from "next/server";

import { requireAuthApi } from "@/lib/auth/guards";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";

export const dynamic = "force-dynamic";

/** Game Environment provider/report status for today's slate -- backs
 * the dashboard's status card and the Settings page. Read-only, so any
 * logged-in user (member or admin) may call it. */
export async function GET() {
  const userOrRes = await requireAuthApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = getTodayChicagoDate();
  const status = await getGameEnvironmentStatus(date);
  if ("error" in status) {
    return NextResponse.json(status, { status: 502 });
  }
  return NextResponse.json(status);
}
