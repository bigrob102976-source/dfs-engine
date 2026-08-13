import type { LineupSet, PitcherEvaluation, PlayerRow } from "./types";

export interface SearchIndexEntry {
  id: string;
  name: string;
  team: string;
  playerType: "pitcher" | "hitter";
  inPitcherSnapshot: boolean;
  inBatterSnapshot: boolean;
  inOwnership: boolean;
  optimizerLineupCount: number;
  inYesterdayEvaluation: boolean;
}

/** Builds one search entry per unique player across every loaded
 * artifact for a slate -- entirely from data already read server-side,
 * no extra I/O per keystroke (search then just filters this array). */
export function buildSearchIndex(params: {
  pitcherRows: PlayerRow[];
  hitterRows: PlayerRow[];
  lineupSet: LineupSet | null;
  pitcherEvaluation: PitcherEvaluation | null;
}): SearchIndexEntry[] {
  const { pitcherRows, hitterRows, lineupSet, pitcherEvaluation } = params;

  const lineupCounts = new Map<string, number>();
  for (const lineup of lineupSet?.lineups ?? []) {
    for (const a of lineup.assignments) {
      const key = a.mlb_player_id ?? a.dk_player_id;
      lineupCounts.set(key, (lineupCounts.get(key) ?? 0) + 1);
    }
  }

  const evaluatedIds = new Set((pitcherEvaluation?.records ?? []).map((r) => String(r.player_id)));

  const entries: SearchIndexEntry[] = [];
  for (const row of [...pitcherRows, ...hitterRows]) {
    entries.push({
      id: row.id,
      name: row.name,
      team: row.team,
      playerType: row.playerType,
      inPitcherSnapshot: row.playerType === "pitcher",
      inBatterSnapshot: row.playerType === "hitter",
      inOwnership: row.ownership !== null,
      optimizerLineupCount: lineupCounts.get(row.id) ?? 0,
      inYesterdayEvaluation: evaluatedIds.has(row.id),
    });
  }
  return entries;
}

export function filterSearchIndex(index: SearchIndexEntry[], query: string): SearchIndexEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return index.filter((e) => e.name.toLowerCase().includes(q) || e.team.toLowerCase().includes(q));
}
