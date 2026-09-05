import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getSavedLineupById } from "@/lib/db/nflSavedLineups";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

interface ExportRequestBody {
  lineupIds: string[];
  /** A REAL DraftKings-exported template CSV (Entry ID/Contest Name/
   * roster columns) the admin/user supplies -- never fabricated by this
   * route. Omit for a roster-only review CSV. */
  template?: string;
}

// NFL M14 -- DK-ready CSV export for saved lineups (nfl/lineup_export.py).
// Every lineup is independently re-validated for structural corruption
// before export -- see that module's own docstring.
export async function POST(request: Request) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  let body: ExportRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Malformed JSON body." }, { status: 400 });
  }

  if (!Array.isArray(body.lineupIds) || body.lineupIds.length === 0) {
    return NextResponse.json({ error: "At least one lineupId is required." }, { status: 400 });
  }

  const savedLineups = [];
  for (const id of body.lineupIds) {
    const row = await getSavedLineupById(id);
    if (!row || row.user_id !== user.id) {
      return NextResponse.json({ error: `Saved lineup ${id} not found.` }, { status: 404 });
    }
    savedLineups.push({
      lineup_id: row.id, sport: "NFL", site: "DraftKings", draft_group_id: row.draft_group_id,
      slate_date: row.slate_date, created_at: row.created_at, updated_at: row.updated_at,
      mode: row.mode, stack_config: JSON.parse(row.stack_config_json), slots: JSON.parse(row.slots_json),
    });
  }

  const requestPayload: Record<string, unknown> = { savedLineups };
  if (typeof body.template === "string" && body.template.length > 0) requestPayload.template = body.template;

  const result = await runPythonScript("scripts/nfl_dashboard_export.py", [JSON.stringify(requestPayload)]);
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
