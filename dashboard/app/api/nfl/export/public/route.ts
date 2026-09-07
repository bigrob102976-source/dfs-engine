import { NextResponse } from "next/server";

import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

interface InlineAssignment {
  slot: string;
  draftkings_player_id: string;
  name: string;
}

interface PublicExportBody {
  lineups: Array<{ assignments: InlineAssignment[] }>;
}

const MAX_LINEUPS = 50;

/** NFL public access -- stateless export of lineup data the CALLER
 * supplies directly in this request (the exact assignments
 * /api/nfl/optimize already returned them in the same session). No
 * auth, no database, no persisted saved-lineup record -- there is no
 * user-owned data this route could ever expose, so no login is
 * required. This is a DIFFERENT route from /api/nfl/export, which
 * operates on persisted, user-owned lineupIds and stays authenticated. */
export async function POST(request: Request) {
  let body: PublicExportBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Malformed JSON body." }, { status: 400 });
  }

  if (!Array.isArray(body.lineups) || body.lineups.length === 0) {
    return NextResponse.json({ error: "At least one lineup is required." }, { status: 400 });
  }
  if (body.lineups.length > MAX_LINEUPS) {
    return NextResponse.json({ error: `At most ${MAX_LINEUPS} lineups may be exported at once.` }, { status: 400 });
  }

  const result = await runPythonScript("scripts/nfl_public_export.py", [JSON.stringify({ lineups: body.lineups })]);
  const parsed = parseLastJsonLine(result.stdout);

  if (result.exitCode !== 0 || !parsed) {
    return NextResponse.json(
      { error: "Failed to run the real NFL export.", details: tail(result.stderr || result.stdout) },
      { status: 502 },
    );
  }
  if (typeof parsed.error === "string") {
    return NextResponse.json({ error: parsed.error, error_type: parsed.error_type ?? null }, { status: 422 });
  }

  return NextResponse.json(parsed);
}
