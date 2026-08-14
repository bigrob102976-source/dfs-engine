import { NextResponse } from "next/server";

import { getTodayChicagoDate } from "@/lib/currentDate";
import { getExternalProjectionsStatus } from "@/lib/externalProjectionsStatus";

export const dynamic = "force-dynamic";

/** External projection provider / baseline / adjusted status for
 * today's slate -- backs the dashboard's status card and the Settings
 * page. See lib/externalProjectionsStatus.ts -- both this route and the
 * server-rendered Settings page share the same underlying call so
 * provider resolution only ever happens in Python. Never returns an API
 * key. */
export async function GET() {
  const date = getTodayChicagoDate();
  const status = await getExternalProjectionsStatus(date);
  if ("error" in status) {
    return NextResponse.json(status, { status: 502 });
  }
  return NextResponse.json(status);
}
