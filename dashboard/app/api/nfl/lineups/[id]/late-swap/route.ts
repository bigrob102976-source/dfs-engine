import { NextResponse } from "next/server";

import { requireAdminApi } from "@/lib/auth/guards";
import { getSavedLineupById, updateSavedLineupSlots } from "@/lib/db/nflSavedLineups";
import { parseLastJsonLine } from "@/lib/optimizerWorkspace/jsonLine";
import { runPythonScript, tail } from "@/lib/orchestrator/pythonRunner";

export const dynamic = "force-dynamic";

interface LateSwapRequestBody {
  mode?: string;
  locks?: string[];
  excludes?: string[];
  stack?: Record<string, unknown>;
  maxExposure?: Record<string, number>;
  maxExposureDefault?: number;
  minExposure?: Record<string, number>;
  /** Test/simulation only -- a real caller never sends this; the Python
   * bridge defaults to the real current UTC time when omitted. */
  nowUtc?: string;
  /** When true, persists the swapped result back onto this saved lineup
   * (slots_json/updated_at) -- when false, this is a preview only. */
  apply?: boolean;
}

// NFL M14 -- runs the REAL late-swap solve (nfl/late_swap.py, itself
// reusing nfl/solver.py's existing CP-SAT engine) against this ONE
// saved lineup. Never a second/duplicate optimizer.
export async function POST(request: Request, ctx: RouteContext<"/api/nfl/lineups/[id]/late-swap">) {
  const userOrRes = await requireAdminApi();
  if (userOrRes instanceof NextResponse) return userOrRes;
  const user = userOrRes;

  const { id } = await ctx.params;
  const row = await getSavedLineupById(id);
  if (!row || row.user_id !== user.id) {
    return NextResponse.json({ error: "Saved lineup not found." }, { status: 404 });
  }

  let body: LateSwapRequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Malformed JSON body." }, { status: 400 });
  }

  const savedLineup = {
    lineup_id: row.id, sport: "NFL", site: "DraftKings", draft_group_id: row.draft_group_id,
    slate_date: row.slate_date, created_at: row.created_at, updated_at: row.updated_at,
    mode: row.mode, stack_config: JSON.parse(row.stack_config_json), slots: JSON.parse(row.slots_json),
  };

  const settings = {
    mode: body.mode || row.mode, locks: body.locks || [], excludes: body.excludes || [],
    stack: body.stack || {}, maxExposure: body.maxExposure || {},
    maxExposureDefault: typeof body.maxExposureDefault === "number" ? body.maxExposureDefault : 1.0,
    minExposure: body.minExposure || {},
  };

  const requestPayload: Record<string, unknown> = { savedLineup, settings };
  if (typeof body.nowUtc === "string") requestPayload.nowUtc = body.nowUtc;

  const result = await runPythonScript("scripts/nfl_dashboard_late_swap.py", [
    String(row.draft_group_id), JSON.stringify(requestPayload),
  ]);
  const parsed = parseLastJsonLine(result.stdout);

  if (result.exitCode !== 0 || !parsed) {
    return NextResponse.json(
      { error: "Failed to run the real NFL late-swap solve.", details: tail(result.stderr || result.stdout) },
      { status: 502 },
    );
  }
  if (typeof parsed.error === "string") {
    return NextResponse.json({ error: parsed.error, error_type: parsed.error_type ?? null }, { status: 422 });
  }

  if (body.apply === true && parsed.lineup) {
    const lineupResult = parsed.lineup as { assignments: unknown[] };
    const newSlots: Array<Record<string, unknown>> = (lineupResult.assignments as Array<Record<string, unknown>>).map((a) => ({
      roster_slot: a.slot, draftkings_player_id: a.draftkings_player_id, name: a.name, team: a.team,
      opponent: null, game_id: "", game_start_utc: null, position: a.position, salary: a.salary,
      projection_snapshot: null, ceiling_snapshot: a.ceiling ?? null, ownership_snapshot: a.projected_ownership ?? null,
    }));
    // Preserve each slot's real game_id/opponent/game_start_utc from the
    // lineup it's replacing (unchanged for locked slots; for a newly
    // swapped-in unlocked player we don't have this from the solve
    // response, so it's left null here -- never fabricated -- and is
    // refreshed the next time this lineup round-trips through a fresh
    // /api/nfl/data-backed save).
    const existingBySlot = new Map((savedLineup.slots as Array<Record<string, unknown>>).map((s) => [s.roster_slot, s]));
    for (const slot of newSlots) {
      const existing = existingBySlot.get(slot.roster_slot as string);
      if (existing && existing.draftkings_player_id === slot.draftkings_player_id) {
        slot.opponent = existing.opponent;
        slot.game_id = existing.game_id;
        slot.game_start_utc = existing.game_start_utc;
        slot.projection_snapshot = existing.projection_snapshot;
      }
    }
    await updateSavedLineupSlots(row.id, JSON.stringify(newSlots));
  }

  return NextResponse.json(parsed);
}
