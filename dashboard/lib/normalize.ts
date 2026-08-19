import type {
  BatterRecord,
  DFSPlayer,
  DKPlayerPool,
  OwnershipPlayer,
  OwnershipSnapshot,
  PitcherRecord,
  PlayerRow,
} from "./types";

function indexByMlbId<T extends { mlb_player_id?: string | null }>(
  rows: T[] | undefined,
): Map<string, T> {
  const map = new Map<string, T>();
  for (const row of rows ?? []) {
    if (row.mlb_player_id) map.set(String(row.mlb_player_id), row);
  }
  return map;
}

/** Milestone 27.2 -- CONFIRMED real bug this fixes: a DK-salaried
 * player whose team's starting lineup hasn't posted yet (or who
 * otherwise has no MLB Stats API match) never got a row at all on
 * Command Center/Pitchers/Hitters/Stacks/Projection Lab, because
 * buildPitcherRows/buildHitterRows below used to iterate ONLY over the
 * research board (pitchers/hitters -- confirmed-lineup-only data), with
 * the DK pool merely enriching a match. Live-confirmed: on 2026-08-18,
 * ALL 52 real LAD @ COL DraftKings rows existed in the DK pool with an
 * honest lineup_status="lineup_not_confirmed", yet zero of them reached
 * any dashboard page because LAD's lineup hadn't posted, so
 * research_output/batters.json (and therefore predictions/*_board_*.json)
 * had zero LAD entries to iterate over -- an entire real MLB team
 * silently vanished from the product, not because of a data problem but
 * because of which array was chosen as "the" row universe.
 *
 * Builds the id->row map from the union of (research board ∪ DK pool)
 * instead: every scored/confirmed player keeps its exact prior row
 * (byte-identical), and every DK pool player with NO board match gets a
 * row too, with every projection/score field honestly null (never
 * invented) and lineupStatus/matchStatus carried through so a page can
 * label it (e.g. "Lineup Not Confirmed") instead of just leaving blanks
 * amid otherwise-normal rows. */
function dkOnlyId(p: DFSPlayer): string {
  return p.mlb_player_id ?? `dk:${p.dk_player_id}`;
}

/** Joins pitcher/batter snapshot records with (optional) ownership and
 * DK-pool data by MLB player ID -- the same canonical join key used
 * throughout the Python pipeline (dfs/player_pool.py, ownership/model.py).
 * Ownership/pool data that isn't loaded yet simply leaves those columns
 * null; nothing here invents a value. */
export function buildPitcherRows(
  pitchers: PitcherRecord[],
  ownership: OwnershipSnapshot | null,
  pool: DKPlayerPool | null,
): PlayerRow[] {
  const ownershipById = indexByMlbId<OwnershipPlayer>(ownership?.players);
  const poolById = indexByMlbId<DFSPlayer>(pool?.players);

  const rows: PlayerRow[] = pitchers.map((p) => {
    const own = ownershipById.get(String(p.player_id)) ?? null;
    const poolPlayer = poolById.get(String(p.player_id)) ?? null;
    return {
      id: String(p.player_id),
      playerType: "pitcher",
      name: p.name,
      team: p.team,
      opponent: p.opponent ?? null,
      gameId: (p.game_id as string) ?? null,
      position: "P",
      positions: ["P"],
      battingOrder: null,
      salary: poolPlayer?.salary ?? (p.salary as number | undefined) ?? null,
      projection: p.projection,
      ceiling: p.ceiling,
      floor: (p.floor as number) ?? null,
      overall: p.overall_score,
      power: null,
      matchup: (p.matchup_score as number) ?? null,
      risk: p.risk_score,
      confidence: p.confidence,
      ownership: own?.projected_ownership ?? null,
      ownershipTier: own?.ownership_tier ?? null,
      chalkScore: own?.chalk_score ?? null,
      leverage: own?.leverage_score ?? null,
      tags: p.tags ?? [],
      reasons: p.reasons ?? [],
      lineupStatus: poolPlayer?.lineup_status ?? null,
      matchStatus: poolPlayer?.match_status ?? null,
      eligibilityStatus: poolPlayer?.eligibility_status ?? null,
      optimizerEligible: poolPlayer?.optimizer_eligible ?? false,
      raw: { snapshot: p, ownership: own, pool: poolPlayer },
    };
  });

  const covered = new Set(rows.map((r) => r.id));
  for (const p of pool?.players ?? []) {
    if (p.player_type !== "pitcher") continue;
    const id = dkOnlyId(p);
    if (covered.has(id)) continue;
    covered.add(id);
    const own = p.mlb_player_id ? (ownershipById.get(p.mlb_player_id) ?? null) : null;
    rows.push({
      id,
      playerType: "pitcher",
      name: p.name,
      team: p.team,
      opponent: p.opponent,
      gameId: p.game_id,
      position: "P",
      positions: ["P"],
      battingOrder: null,
      salary: p.salary,
      projection: p.projection,
      ceiling: p.ceiling,
      floor: p.floor,
      overall: p.overall_score,
      power: null,
      matchup: null,
      risk: p.risk_score,
      confidence: p.confidence,
      ownership: own?.projected_ownership ?? null,
      ownershipTier: own?.ownership_tier ?? null,
      chalkScore: own?.chalk_score ?? null,
      leverage: own?.leverage_score ?? null,
      tags: p.tags ?? [],
      reasons: p.reasons ?? [],
      lineupStatus: p.lineup_status,
      matchStatus: p.match_status,
      eligibilityStatus: p.eligibility_status ?? null,
      optimizerEligible: p.optimizer_eligible ?? false,
      raw: { snapshot: {}, ownership: own, pool: p },
    });
  }

  return rows;
}

export function buildHitterRows(
  hitters: BatterRecord[],
  ownership: OwnershipSnapshot | null,
  pool: DKPlayerPool | null,
): PlayerRow[] {
  const ownershipById = indexByMlbId<OwnershipPlayer>(ownership?.players);
  const poolById = indexByMlbId<DFSPlayer>(pool?.players);

  const rows: PlayerRow[] = hitters.map((h) => {
    const own = ownershipById.get(String(h.player_id)) ?? null;
    const poolPlayer = poolById.get(String(h.player_id)) ?? null;
    const positions = poolPlayer?.dk_positions ?? (h.position ? [h.position] : []);
    return {
      id: String(h.player_id),
      playerType: "hitter",
      name: h.name,
      team: h.team,
      opponent: h.opponent ?? null,
      gameId: (h.game_id as string) ?? null,
      position: positions[0] ?? h.position ?? null,
      positions,
      battingOrder: h.batting_order,
      salary: poolPlayer?.salary ?? (h.salary as number | undefined) ?? null,
      projection: h.projection,
      ceiling: h.ceiling,
      floor: (h.floor as number) ?? null,
      overall: h.overall_score,
      power: (h.power_score as number) ?? null,
      matchup: (h.matchup_score as number) ?? null,
      risk: h.risk_score,
      confidence: h.confidence,
      ownership: own?.projected_ownership ?? null,
      ownershipTier: own?.ownership_tier ?? null,
      chalkScore: own?.chalk_score ?? null,
      leverage: own?.leverage_score ?? null,
      tags: h.tags ?? [],
      reasons: h.reasons ?? [],
      lineupStatus: poolPlayer?.lineup_status ?? null,
      matchStatus: poolPlayer?.match_status ?? null,
      eligibilityStatus: poolPlayer?.eligibility_status ?? null,
      optimizerEligible: poolPlayer?.optimizer_eligible ?? false,
      raw: { snapshot: h, ownership: own, pool: poolPlayer },
    };
  });

  const covered = new Set(rows.map((r) => r.id));
  for (const p of pool?.players ?? []) {
    if (p.player_type !== "hitter") continue;
    const id = dkOnlyId(p);
    if (covered.has(id)) continue;
    covered.add(id);
    const own = p.mlb_player_id ? (ownershipById.get(p.mlb_player_id) ?? null) : null;
    rows.push({
      id,
      playerType: "hitter",
      name: p.name,
      team: p.team,
      opponent: p.opponent,
      gameId: p.game_id,
      position: p.dk_positions[0] ?? null,
      positions: p.dk_positions,
      battingOrder: p.batting_order,
      salary: p.salary,
      projection: p.projection,
      ceiling: p.ceiling,
      floor: p.floor,
      overall: p.overall_score,
      power: null,
      matchup: null,
      risk: p.risk_score,
      confidence: p.confidence,
      ownership: own?.projected_ownership ?? null,
      ownershipTier: own?.ownership_tier ?? null,
      chalkScore: own?.chalk_score ?? null,
      leverage: own?.leverage_score ?? null,
      tags: p.tags ?? [],
      reasons: p.reasons ?? [],
      lineupStatus: p.lineup_status,
      matchStatus: p.match_status,
      eligibilityStatus: p.eligibility_status ?? null,
      optimizerEligible: p.optimizer_eligible ?? false,
      raw: { snapshot: {}, ownership: own, pool: p },
    });
  }

  return rows;
}
