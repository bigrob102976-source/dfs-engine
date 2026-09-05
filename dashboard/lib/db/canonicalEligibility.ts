import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { runPythonScript, tail } from "../orchestrator/pythonRunner";
import { resolveMlbPlayerIds } from "./canonicalPlayerIdentity";
import { getExecutor } from "./executor";
import type { CanonicalSlatePlayerRow, CanonicalSlateRow } from "./types";

// M6A/M6B/M6C/M6D -- the Python<->Postgres eligibility bridge. Reuses
// dfs/eligibility.py::compute_eligibility() and dfs/slate_validation.py
// ::match_game_infos() UNCHANGED (M6 rules #11/#12), invoked as a
// subprocess (scripts/compute_canonical_eligibility.py) via the SAME
// runPythonScript() every other Python-spawning call in this codebase
// uses (see poolCache.ts). Python never touches Postgres directly (see
// canonical_ingestion/__init__.py's own documented reason) -- this
// module is the ONE place that reads canonical Postgres, builds the
// JSON payload the Python script expects, and persists its real results
// back onto slate_players' CURRENT state (never a new row, never
// touching immutable RAW/NORMALIZED artifacts -- M6E).

export interface EligibilityComputeResult {
  status: "OK" | "NO_RESEARCH_PACKAGE" | "SLATE_NOT_FOUND" | "ERROR";
  reason?: string;
  playersUpdated: number;
}

interface EligibilityPlayerResult {
  providerPlayerId: string;
  gameId: string | null;
  eligibilityStatus: string;
  optimizerEligible: boolean;
  battingOrder: number | null;
  // PROBABLE FIX: additive -- see dfs/eligibility.py's own docstring for
  // the full CONFIRMED/PROBABLE mapping. lineupConfirmation is null for
  // every status where it doesn't apply; probableConfidence/
  // probableReason/projectedBattingOrder are only ever set alongside
  // eligibilityStatus === "PROBABLE_HITTER".
  lineupConfirmation: string | null;
  probableConfidence: string | null;
  probableReason: string | null;
  projectedBattingOrder: number | null;
}

function parseJsonArray(json: string | null): string[] {
  if (!json) return [];
  try {
    const parsed = JSON.parse(json);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function parseResultJson(stdout: string): { status: string; reason?: string; results: EligibilityPlayerResult[] } | null {
  for (const line of stdout.split("\n").reverse()) {
    if (line.startsWith("RESULT_JSON:")) {
      try {
        return JSON.parse(line.slice("RESULT_JSON:".length));
      } catch {
        return null;
      }
    }
  }
  return null;
}

/** M6J: writes the eligibility-input payload to a unique file under the
 * OS temp directory (never a path derived from request input -- the
 * server always generates this path itself), invokes the real Python
 * bridge, and ALWAYS cleans up in a finally block, mirroring
 * buildRunner.ts's own writeProjectionOverridesFile/
 * cleanupProjectionOverridesFile convention exactly. */
export interface EligibilityRefreshForDateResult {
  date: string;
  slatesFound: number;
  slatesUpdated: number;
  slatesFailed: number;
  perSlate: Array<{ internalSlateId: string; providerSlateId: string } & EligibilityComputeResult>;
}

/** M7A/M7B -- the ONE function the existing research-refresh path
 * (lib/slatePipeline.ts::runSlatePipeline, the same "Process Slate"/
 * "Refresh Data" admin action that already re-runs
 * scripts/build_research_package.py on every call -- see that
 * function's own M32.7 comment) calls after a research refresh, so
 * canonical eligibility recomputes automatically with NO separate
 * scheduler/polling loop and NO second research fetch (M7 rules #5/#6).
 * Recomputes EVERY real, currently-VALID canonical slate for `date`
 * (M7B: a research refresh may cover several real Classic slates) --
 * one slate's failure is caught and reported per-slate, never stopping
 * the others (M7B) and never thrown to the caller (M7A/M7J: the legacy
 * research-refresh/pipeline success must never depend on this). */
export async function refreshCanonicalEligibilityForDate(date: string, sport: string = "MLB"): Promise<EligibilityRefreshForDateResult> {
  const db = getExecutor();
  const slates = await db.all<{ internal_slate_id: string; provider_slate_id: string }>(
    "SELECT internal_slate_id, provider_slate_id FROM slates WHERE sport = ? AND slate_date = ? AND validation_state = 'VALID'",
    [sport, date],
  );
  if (slates.length === 0) {
    return { date, slatesFound: 0, slatesUpdated: 0, slatesFailed: 0, perSlate: [] };
  }

  // MLB AUTOMATIC PIPELINE RELIABILITY: root-caused live -- the real
  // MLB-Stats-API-bound probable-hitter inference
  // (dfs/probable_starters.py::build_probable_hitters_map, invoked from
  // scripts/compute_canonical_eligibility.py) iterates the WHOLE
  // research package's games for `date`, completely independent of
  // which slate's players were passed in. Calling
  // computeAndPersistEligibilityForSlate once PER SLATE (the previous
  // design) therefore redundantly repeated the SAME real, ~90-170s
  // network-bound computation once per slate for absolutely no reason --
  // measured live: 30 teams x ~3-6s each, EVERY time, for a date with 4
  // real slates. This is what was exceeding the worker's remote timeout.
  // The SAME real player appearing on more than one of a date's slates
  // has the exact same real eligibility (it's derived from team/game/
  // date, never from which slate a row happens to live under), so
  // computing it ONCE for the date and persisting the SAME result onto
  // every slate's own slate_players rows is correct, not an
  // approximation -- never a second, divergent eligibility computation
  // (M6 rules #11/#12 still hold: this still calls
  // scripts/compute_canonical_eligibility.py exactly once, just with a
  // combined, deduplicated player set instead of once per slate).
  let dateResult: { status: "OK" | "NO_RESEARCH_PACKAGE" | "ERROR"; reason?: string; resultsByProviderPlayerId: Map<string, EligibilityPlayerResult> };
  try {
    dateResult = await computeEligibilityForDate(date, slates);
  } catch (err) {
    dateResult = { status: "ERROR", reason: err instanceof Error ? err.message : String(err), resultsByProviderPlayerId: new Map() };
  }

  const perSlate: EligibilityRefreshForDateResult["perSlate"] = [];
  for (const slate of slates) {
    if (dateResult.status !== "OK") {
      perSlate.push({
        internalSlateId: slate.internal_slate_id, providerSlateId: slate.provider_slate_id,
        status: dateResult.status, reason: dateResult.reason, playersUpdated: 0,
      });
      continue;
    }
    // Persistence stays per-slate (own try/catch, own row scope) even
    // though the compute step above is shared -- one slate's write-back
    // failing must never affect another's, and reporting stays accurate
    // per slate.
    try {
      const playersUpdated = await persistEligibilityResultsForSlate(slate.internal_slate_id, dateResult.resultsByProviderPlayerId);
      perSlate.push({ internalSlateId: slate.internal_slate_id, providerSlateId: slate.provider_slate_id, status: "OK", playersUpdated });
    } catch (err) {
      perSlate.push({
        internalSlateId: slate.internal_slate_id, providerSlateId: slate.provider_slate_id,
        status: "ERROR", reason: err instanceof Error ? err.message : String(err), playersUpdated: 0,
      });
    }
  }

  return {
    date,
    slatesFound: slates.length,
    slatesUpdated: perSlate.filter((s) => s.status === "OK").length,
    slatesFailed: perSlate.filter((s) => s.status !== "OK").length,
    perSlate,
  };
}

/** The shared, date-level compute step -- builds ONE deduplicated player
 * payload across every one of the date's real, currently-VALID slates
 * (the same real player appearing on more than one slate contributes
 * only once; the DB write-back step below still updates every slate's
 * own row for that player), calls the real Python bridge exactly once,
 * and returns its results indexed by providerPlayerId for the caller to
 * distribute back per slate. Never throws for an honest
 * NO_RESEARCH_PACKAGE/subprocess failure -- only a genuinely unexpected
 * exception propagates, matching computeAndPersistEligibilityForSlate's
 * own contract. */
async function computeEligibilityForDate(
  date: string, slates: Array<{ internal_slate_id: string; provider_slate_id: string }>,
): Promise<{ status: "OK" | "NO_RESEARCH_PACKAGE" | "ERROR"; reason?: string; resultsByProviderPlayerId: Map<string, EligibilityPlayerResult> }> {
  const db = getExecutor();
  const placeholders = slates.map(() => "?").join(",");
  const playerRows = await db.all<CanonicalSlatePlayerRow>(
    `SELECT * FROM slate_players WHERE internal_slate_id IN (${placeholders})`,
    slates.map((s) => s.internal_slate_id),
  );

  // Deduplicate by providerPlayerId -- first occurrence wins (team/
  // opponent/positions/salary/identityStatus for the SAME real player on
  // the SAME real date are the same real facts regardless of which
  // slate's row is read first).
  const uniquePlayersByProviderId = new Map<string, CanonicalSlatePlayerRow>();
  for (const row of playerRows) {
    if (!uniquePlayersByProviderId.has(row.provider_player_id)) uniquePlayersByProviderId.set(row.provider_player_id, row);
  }
  const uniqueRows = [...uniquePlayersByProviderId.values()];

  const resolvedInternalPlayerIds = uniqueRows.map((p) => p.internal_player_id).filter((id): id is string => id !== null);
  const mlbIdByInternalPlayerId = await resolveMlbPlayerIds(resolvedInternalPlayerIds);

  const payload = {
    date,
    players: uniqueRows.map((p) => ({
      providerPlayerId: p.provider_player_id,
      name: p.name,
      team: p.team,
      opponent: p.opponent,
      positions: parseJsonArray(p.position_eligibility_json),
      salary: p.salary,
      identityStatus: p.identity_status,
      mlbPlayerId: p.internal_player_id ? (mlbIdByInternalPlayerId.get(p.internal_player_id) ?? null) : null,
    })),
  };

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-canonical-eligibility-date-"));
  const inputPath = path.join(dir, "players.json");
  try {
    fs.writeFileSync(inputPath, JSON.stringify(payload), "utf-8");

    const result = await runPythonScript("scripts/compute_canonical_eligibility.py", ["--date", date, "--input", inputPath]);
    const parsed = parseResultJson(result.stdout);
    if (!parsed) {
      return { status: "ERROR", reason: `Unexpected eligibility computation failure: ${tail(result.stdout + result.stderr, 1000)}`, resultsByProviderPlayerId: new Map() };
    }
    if (parsed.status === "NO_RESEARCH_PACKAGE") {
      return { status: "NO_RESEARCH_PACKAGE", reason: parsed.reason, resultsByProviderPlayerId: new Map() };
    }

    const resultsByProviderPlayerId = new Map<string, EligibilityPlayerResult>();
    for (const r of parsed.results) resultsByProviderPlayerId.set(r.providerPlayerId, r);
    return { status: "OK", resultsByProviderPlayerId };
  } finally {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup of an OS temp file -- never fail eligibility computation over this.
    }
  }
}

/** Applies the shared date-level compute result onto ONE slate's own
 * slate_players rows -- unchanged persistence semantics from the
 * previous per-slate implementation (same UPDATE statement, same
 * columns), just fed from a shared result map instead of a fresh
 * per-slate subprocess call. A player row with no matching result
 * (should not normally happen -- every row contributed to the shared
 * payload) is left untouched rather than guessed at. */
async function persistEligibilityResultsForSlate(internalSlateId: string, resultsByProviderPlayerId: Map<string, EligibilityPlayerResult>): Promise<number> {
  const db = getExecutor();
  const playerRows = await db.all<{ provider_player_id: string }>("SELECT provider_player_id FROM slate_players WHERE internal_slate_id = ?", [internalSlateId]);

  const now = new Date().toISOString();
  let playersUpdated = 0;
  await db.transaction(async (tx) => {
    for (const row of playerRows) {
      const r = resultsByProviderPlayerId.get(row.provider_player_id);
      if (!r) continue;
      await tx.run(
        `UPDATE slate_players SET game_id = ?, eligibility_status = ?, optimizer_eligible = ?, batting_order = ?,
           lineup_confirmation = ?, probable_confidence = ?, probable_reason = ?, projected_batting_order = ?,
           eligibility_computed_at = ?, updated_at = ?
         WHERE internal_slate_id = ? AND provider_player_id = ?`,
        [
          r.gameId, r.eligibilityStatus, r.optimizerEligible ? 1 : 0, r.battingOrder,
          r.lineupConfirmation ?? null, r.probableConfidence ?? null, r.probableReason ?? null, r.projectedBattingOrder ?? null,
          now, now, internalSlateId, row.provider_player_id,
        ],
      );
      playersUpdated += 1;
    }
  });
  return playersUpdated;
}

export async function computeAndPersistEligibilityForSlate(internalSlateId: string): Promise<EligibilityComputeResult> {
  const db = getExecutor();
  const slate = await db.get<CanonicalSlateRow>("SELECT * FROM slates WHERE internal_slate_id = ?", [internalSlateId]);
  if (!slate) return { status: "SLATE_NOT_FOUND", playersUpdated: 0 };

  const playerRows = await db.all<CanonicalSlatePlayerRow>("SELECT * FROM slate_players WHERE internal_slate_id = ?", [internalSlateId]);
  const resolvedInternalPlayerIds = playerRows.map((p) => p.internal_player_id).filter((id): id is string => id !== null);
  const mlbIdByInternalPlayerId = await resolveMlbPlayerIds(resolvedInternalPlayerIds);

  const payload = {
    date: slate.slate_date,
    players: playerRows.map((p) => ({
      providerPlayerId: p.provider_player_id,
      name: p.name,
      team: p.team,
      opponent: p.opponent,
      positions: parseJsonArray(p.position_eligibility_json),
      salary: p.salary,
      identityStatus: p.identity_status,
      mlbPlayerId: p.internal_player_id ? (mlbIdByInternalPlayerId.get(p.internal_player_id) ?? null) : null,
    })),
  };

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-canonical-eligibility-"));
  const inputPath = path.join(dir, "players.json");
  try {
    fs.writeFileSync(inputPath, JSON.stringify(payload), "utf-8");

    const result = await runPythonScript("scripts/compute_canonical_eligibility.py", ["--date", slate.slate_date, "--input", inputPath]);
    const parsed = parseResultJson(result.stdout);
    if (!parsed) {
      return { status: "ERROR", reason: `Unexpected eligibility computation failure: ${tail(result.stdout + result.stderr, 1000)}`, playersUpdated: 0 };
    }
    if (parsed.status === "NO_RESEARCH_PACKAGE") {
      return { status: "NO_RESEARCH_PACKAGE", reason: parsed.reason, playersUpdated: 0 };
    }

    const now = new Date().toISOString();
    await db.transaction(async (tx) => {
      for (const r of parsed.results) {
        await tx.run(
          `UPDATE slate_players SET game_id = ?, eligibility_status = ?, optimizer_eligible = ?, batting_order = ?,
             lineup_confirmation = ?, probable_confidence = ?, probable_reason = ?, projected_batting_order = ?,
             eligibility_computed_at = ?, updated_at = ?
           WHERE internal_slate_id = ? AND provider_player_id = ?`,
          [
            r.gameId, r.eligibilityStatus, r.optimizerEligible ? 1 : 0, r.battingOrder,
            // PROBABLE FIX: coalesced to null -- better-sqlite3 rejects a
            // bare `undefined` bind param, and these fields are absent
            // (not merely null) on any result JSON produced before this
            // milestone (e.g. an older cached/mocked runner response).
            r.lineupConfirmation ?? null, r.probableConfidence ?? null, r.probableReason ?? null, r.projectedBattingOrder ?? null,
            now, now, internalSlateId, r.providerPlayerId,
          ],
        );
      }
    });

    return { status: "OK", playersUpdated: parsed.results.length };
  } finally {
    try {
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup of an OS temp file -- never fail eligibility computation over this.
    }
  }
}
