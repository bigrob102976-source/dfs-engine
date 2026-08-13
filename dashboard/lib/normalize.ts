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

  return pitchers.map((p) => {
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
      raw: { snapshot: p, ownership: own, pool: poolPlayer },
    };
  });
}

export function buildHitterRows(
  hitters: BatterRecord[],
  ownership: OwnershipSnapshot | null,
  pool: DKPlayerPool | null,
): PlayerRow[] {
  const ownershipById = indexByMlbId<OwnershipPlayer>(ownership?.players);
  const poolById = indexByMlbId<DFSPlayer>(pool?.players);

  return hitters.map((h) => {
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
      raw: { snapshot: h, ownership: own, pool: poolPlayer },
    };
  });
}
