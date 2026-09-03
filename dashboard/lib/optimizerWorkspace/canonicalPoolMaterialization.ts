import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import type { OptimizerPoolResult, PoolPlayerRow } from "./types";

// M6I/M6J -- the canonical-serving-to-optimizer bridge. Converts an
// already-loaded CanonicalPostgresServingBackend pool (real salaries/
// positions/teams/eligibility -- see canonicalPostgresBackend.ts) into
// the EXACT dk_player_pool_<ts>.json shape dfs/models.py::DFSPlayer.
// to_dict() produces, so scripts/optimize_dk_lineups.py (unmodified,
// same CP-SAT solver every legacy build already uses) can read it via
// its existing --pool <path> flag -- never a forked/divergent optimizer
// algorithm (M6I).
//
// MLB FINISH MODE Phase B/D: projection/ceiling/floor were ALWAYS null
// here through M6-M8 (canonical Postgres had no projection source in
// those milestones) -- now that canonicalPostgresBackend.ts's own
// poolPlayerRowFromCanonical() populates real Big Money Native values
// (via canonicalProjections.ts), this function simply passes those real
// values through unchanged. Still never fabricates: a player with no
// persisted projection row (unresolved identity, or the Native engine
// genuinely has no coverage for them) keeps null here exactly as
// before, and scripts/optimize_dk_lineups.py's own
// _build_optimizer_players() continues to correctly (and honestly)
// exclude any such player from the solver -- same real, unmodified
// exclusion behavior, just now with real data feeding it instead of an
// always-empty pool.
function dfsPlayerDict(p: PoolPlayerRow): Record<string, unknown> {
  return {
    dk_player_id: p.dkPlayerId, name: p.name, team: p.team, player_type: p.playerType,
    dk_positions: p.positions, salary: p.salary,
    mlb_player_id: p.mlbPlayerId, opponent: p.opponent, game_id: p.gameId,
    // PROBABLE FIX: a PROBABLE_HITTER never has a real CONFIRMED
    // battingOrder (dfs/eligibility.py only ever sets that once the
    // official lineup posts) -- fall back to the real, evidence-based
    // projectedBattingOrder so the ownership model isn't starved of a
    // batting-order signal just because the lineup hasn't posted yet.
    // eligibility_status/lineup_confirmation below still tell the real
    // story honestly either way.
    batting_order: p.battingOrder ?? p.projectedBattingOrder ?? null, throwing_hand: null, batting_hand: null,
    projection: p.projection, ceiling: p.ceiling, floor: p.nativeFloor,
    overall_score: null, risk_score: null, confidence: p.nativeConfidence,
    tags: [], reasons: p.nativeReasons ?? [],
    season_sample_size: null, recent_sample_size: null,
    source_model_type: p.playerType, source_model_version: null,
    prediction_generated_at_utc: null, prediction_generated_at_local: null, prediction_snapshot_path: null,
    lineup_status: p.lineupStatus, match_status: p.matchStatus, match_confidence: null,
    eligibility_status: p.eligibilityStatus, optimizer_eligible: p.optimizerEligible,
    avg_points_per_game_dk: null, dk_status: null, dk_starting: null,
    source_row_number: null, source_filename: null, source_sha256: null,
  };
}

/** M6J temp-file safety: OS temp directory, unique mkdtemp-generated
 * name, server-generated path only (never derived from request input),
 * bounded to exactly this pool's own real player count (no unbounded
 * growth), cleaned up by the caller's own finally block via
 * cleanupCanonicalPoolFile -- mirrors buildRunner.ts's own
 * writeProjectionOverridesFile/cleanupProjectionOverridesFile
 * convention exactly, never a new pattern. */
export function materializeCanonicalPoolFile(pool: OptimizerPoolResult): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mlb-dfs-canonical-pool-"));
  const filePath = path.join(dir, "dk_player_pool.json");
  const doc = {
    slate_date: pool.date,
    generated_at_utc: pool.generatedAt,
    pitcher_snapshot_path: null,
    batter_snapshot_path: null,
    roster_feasibility_pass: pool.rosterFeasibilityPass,
    provider_source: pool.providerSource,
    selected_slate_id: pool.slateId,
    player_count: pool.players.length,
    players: pool.players.map(dfsPlayerDict),
  };
  fs.writeFileSync(filePath, JSON.stringify(doc), "utf-8");
  return filePath;
}

export function cleanupCanonicalPoolFile(filePath: string | null): void {
  if (!filePath) return;
  try {
    fs.rmSync(path.dirname(filePath), { recursive: true, force: true });
  } catch {
    // Best-effort cleanup of an OS temp file -- never fail a build over this.
  }
}
