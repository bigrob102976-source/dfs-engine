import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";

export const dynamic = "force-dynamic";

export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = getTodayChicagoDate();
  return NextResponse.json({
    date,
    summary: buildSlateSummary(date),
    statuses: buildPipelineStatuses(date),
  });
}
