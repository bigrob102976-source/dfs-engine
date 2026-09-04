import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

interface OptimizeRequestBody {
  draftGroupId: number;
  numLineups: number;
  mode?: "roster_feasibility" | "projection";
  locks?: string[];
  excludes?: string[];
}

// NFL UI M1 -- runs the REAL nfl/solver.py CP-SAT optimizer (via
// scripts/nfl_dashboard_optimize.py) -- never a reimplementation, never
// a fabricated "feasible" result. Locks/excludes are DraftKings player
// IDs, passed through as opaque strings to the real solver, which is
// itself the only thing that decides feasibility.
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  let body: OptimizeRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Malformed JSON body." }, { status: 400 });
  }

  if (!Number.isInteger(body.draftGroupId) || body.draftGroupId <= 0) {
    return NextResponse.json({ error: "A valid draftGroupId is required." }, { status: 400 });
  }
  const numLineups = Number.isInteger(body.numLineups) && body.numLineups > 0 ? Math.min(body.numLineups, 20) : 1;
  const mode = body.mode === "projection" ? "projection" : "roster_feasibility";
  const locks = Array.isArray(body.locks) ? body.locks.filter((v) => typeof v === "string") : [];
  const excludes = Array.isArray(body.excludes) ? body.excludes.filter((v) => typeof v === "string") : [];

  const args = [String(body.draftGroupId), String(numLineups), mode, locks.join(","), excludes.join(",")];
  const result = await runPythonScript("scripts/nfl_dashboard_optimize.py", args);
  const parsed = parseLastJsonLine(result.stdout);

  if (result.exitCode !== 0 || !parsed) {
    return NextResponse.json(
      { error: "Failed to run the real NFL optimizer.", details: tail(result.stderr || result.stdout) },
      { status: 502 },
    );
  }
  if (typeof parsed.error === "string") {
    return NextResponse.json({ error: parsed.error, error_type: parsed.error_type ?? null }, { status: 422 });
  }

  return NextResponse.json(parsed);
}
