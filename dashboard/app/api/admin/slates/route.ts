import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getTodayEasternDate } from "@/lib/currentDate";
import { buildPipelineStatuses, buildSlateSummary } from "@/lib/pipelineStatus";

export const dynamic = "force-dynamic";

export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = getTodayEasternDate();
  const [summary, statuses] = await Promise.all([buildSlateSummary(date), buildPipelineStatuses(date)]);
  return NextResponse.json({ date, summary, statuses });
}
