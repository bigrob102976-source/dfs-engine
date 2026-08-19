import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getTodayChicagoDate } from "@/lib/currentDate";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

interface GenerateResult {
  status: "ready" | "no_research";
  path?: string;
  game_count?: number;
  reason?: string;
}

/** Manually builds today's Game Environment snapshot on demand (research/
 * game_environment/engine.py via scripts/build_game_environment_report.py).
 * Deliberately separate from /api/refresh -- the environment engine reads
 * an already-built Research Package and never touches projections, ownership,
 * or the optimizer, so it doesn't belong in that pipeline. Milestone 29:
 * admin-only -- generating/refreshing backend slate data is an admin action. */
export async function POST() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const date = getTodayChicagoDate();
  const result = await runPythonScript("scripts/build_game_environment_report.py", ["--date", date]);
  const doc = parseLastJsonLine(result.stdout) as unknown as GenerateResult | null;

  if (!doc) {
    return NextResponse.json({ error: `Unexpected environment-report generation failure: ${tail(result.stdout + result.stderr, 500)}` }, { status: 502 });
  }
  if (doc.status === "no_research") {
    return NextResponse.json({ error: doc.reason ?? "No research package found for today's slate." }, { status: 409 });
  }
  return NextResponse.json(doc);
}
