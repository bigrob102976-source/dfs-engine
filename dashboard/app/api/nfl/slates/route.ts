import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

// NFL UI M1 -- real DraftKings NFL Classic slate discovery (never
// hardcoded to one DraftGroup; scripts/nfl_dashboard_slates.py is the
// same real discovery path scripts/nfl_dashboard_data.py itself uses).
export async function GET() {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;

  const result = await runPythonScript("scripts/nfl_dashboard_slates.py", []);
  const parsed = parseLastJsonLine(result.stdout);

  if (result.exitCode !== 0 || !parsed) {
    return NextResponse.json(
      { error: "Failed to discover real NFL slates.", details: tail(result.stderr || result.stdout) },
      { status: 502 },
    );
  }
  if (typeof parsed.error === "string") {
    return NextResponse.json({ error: parsed.error }, { status: 422 });
  }

  return NextResponse.json(parsed);
}
