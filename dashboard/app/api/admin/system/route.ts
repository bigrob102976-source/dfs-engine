import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getTodayEasternDate } from "@/lib/currentDate";
import { computeDbStats } from "@/lib/db/systemStats";
import { getExternalProjectionsStatus } from "@/lib/externalProjectionsStatus";
import { getGameEnvironmentStatus } from "@/lib/gameEnvironmentStatus";
import { getMockModeEnabled } from "@/lib/mockMode";

export const dynamic = "force-dynamic";

export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = getTodayEasternDate();
  const [mockModeEnabled, externalProjections, gameEnvironment] = await Promise.all([
    getMockModeEnabled(),
    getExternalProjectionsStatus(date),
    getGameEnvironmentStatus(date),
  ]);

  return NextResponse.json({
    db: await computeDbStats(),
    mockModeEnabled,
    externalProjections,
    gameEnvironment,
  });
}
