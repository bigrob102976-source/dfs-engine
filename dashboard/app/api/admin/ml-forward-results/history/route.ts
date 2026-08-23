import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

/** Milestone 32.5 -- cumulative forward-history windows (1/3/5/10/all
 * completed slates), computed by evaluation/ml_forward_history.py
 * (pooled MAE/RMSE/Pearson/Spearman recomputed correctly across
 * slates, never algebraically approximated). ADMIN only. */
export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const result = await runPythonScript("scripts/run_ml_forward_history.py", []);
  if (result.exitCode !== 0) {
    return NextResponse.json({ error: `History computation failed: ${tail(result.stdout + result.stderr, 1500)}` }, { status: 502 });
  }

  const body = parseLastJsonLine(result.stdout);
  return NextResponse.json({ history: body?.history ?? null });
}
