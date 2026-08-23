import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";
import { resolveSlateDate } from "@/lib/slateDate";

export const dynamic = "force-dynamic";

/** Milestone 32.5 -- the "COLLECT RESULTS" admin action: checks MLB
 * FINAL status for this slate, collects + scores whatever games are
 * final, grades every ML/Native/AI/FantasyPros player and every saved
 * M32.4 lineup set, and persists one immutable ml_forward_results
 * document (scripts/collect_ml_forward_results.py). Safe to call
 * repeatedly -- a slate that isn't fully final yet still runs and
 * reports PARTIAL results honestly; a fully-final slate produces a new
 * immutable snapshot each call (never overwrites a prior one). ADMIN
 * only, same gating as the Big Money ML optimizer source itself. */
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Request body must be JSON." }, { status: 400 });
  }

  const slateId = (body as { slateId?: unknown } | null)?.slateId;
  if (typeof slateId !== "string" || slateId.length === 0) {
    return NextResponse.json({ error: "\"slateId\" (string) is required." }, { status: 400 });
  }
  const dateResolution = resolveSlateDate((body as { date?: unknown } | null)?.date);
  if (!dateResolution.ok) {
    return NextResponse.json({ error: dateResolution.error }, { status: 400 });
  }

  const result = await runPythonScript("scripts/collect_ml_forward_results.py", ["--date", dateResolution.date, "--slate-id", slateId]);
  if (result.exitCode !== 0) {
    return NextResponse.json({ error: `Collection failed: ${tail(result.stdout + result.stderr, 1500)}` }, { status: 502 });
  }

  const status = parseLastJsonLine(result.stdout);
  return NextResponse.json({ status, stdout: tail(result.stdout, 4000) });
}
