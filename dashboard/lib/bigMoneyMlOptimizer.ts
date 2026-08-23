// Milestone 32.4: Big Money ML owner-optimizer coverage gate. Pure,
// read-only composition of the M32.3B ML snapshot documents (already
// carry their own eligible/generated/missing counts, computed by
// big_money_ml/hitter_shadow_inference.py and shadow_inference.py from
// the SAME M30.1 eligibility denominator the optimizer pool itself
// uses) plus the current DK player pool -- never recomputes eligibility
// itself, never triggers generation.

import { loadLatestDKPlayerPool } from "./loaders";
import { getBigMoneyMlProvenance, loadLatestMlHitterProjectionSnapshot, loadLatestMlProjectionSnapshot } from "./mlProjections";
import type { DKPlayerPool } from "./types";

export interface BigMoneyMlSourceCoverage {
  generated: number;
  eligible: number;
}

export interface BigMoneyMlCoverage {
  pitchers: BigMoneyMlSourceCoverage;
  hitters: BigMoneyMlSourceCoverage;
  combined: BigMoneyMlSourceCoverage;
  gamesWaitingForLineups: number;
  pitcherModelVersion: string | null;
  hitterModelVersion: string | null;
  pitcherSnapshotGeneratedAt: string | null;
  hitterSnapshotGeneratedAt: string | null;
}

/** A game "waiting for lineups" is one with at least one hitter in the
 * DK pool but NO confirmed (STARTING_HITTER) hitter yet -- the same
 * unconfirmed/confirmed distinction dfs/eligibility.py already draws,
 * just grouped by game_id here for display. Pitcher-only games (a
 * doubleheader edge case) are never counted since this reflects hitter
 * lineup posting specifically. */
function countGamesWaitingForLineups(pool: DKPlayerPool | null): number {
  if (!pool) return 0;
  const gameIds = new Set<string>();
  const confirmedGameIds = new Set<string>();
  for (const p of pool.players) {
    if (p.player_type !== "hitter" || !p.game_id) continue;
    gameIds.add(p.game_id);
    if (p.eligibility_status === "STARTING_HITTER") confirmedGameIds.add(p.game_id);
  }
  let waiting = 0;
  for (const gameId of gameIds) {
    if (!confirmedGameIds.has(gameId)) waiting += 1;
  }
  return waiting;
}

/** The BIG MONEY ML COVERAGE gate: shown to ADMIN before an ML
 * optimizer build. Reads the M30.1 eligibility denominator directly
 * from the persisted ML snapshots -- never recomputed here. */
export function getBigMoneyMlCoverage(date: string, slateId?: string | null): BigMoneyMlCoverage {
  const pitcherDoc = loadLatestMlProjectionSnapshot(date);
  const hitterDoc = loadLatestMlHitterProjectionSnapshot(date);
  const pool = loadLatestDKPlayerPool(date, slateId ?? null).data;

  const pitchers: BigMoneyMlSourceCoverage = {
    generated: pitcherDoc?.ml_projections_generated ?? 0,
    eligible: pitcherDoc?.ml_eligible_pitcher_count ?? 0,
  };
  const hitters: BigMoneyMlSourceCoverage = {
    generated: hitterDoc?.ml_projections_generated ?? 0,
    eligible: hitterDoc?.ml_eligible_hitter_count ?? 0,
  };
  const combined: BigMoneyMlSourceCoverage = {
    generated: pitchers.generated + hitters.generated,
    eligible: pitchers.eligible + hitters.eligible,
  };

  return {
    pitchers,
    hitters,
    combined,
    gamesWaitingForLineups: countGamesWaitingForLineups(pool),
    ...getBigMoneyMlProvenance(date),
  };
}
