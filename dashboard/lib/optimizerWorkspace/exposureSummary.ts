import type { Lineup } from "../types";
import type { ExposureRow, StackExposureRow } from "./types";

/** Player-level exposure across a generated lineup set -- sorted by
 * exposure % descending. `playerTypeFilter` narrows to a single type
 * (e.g. "pitcher" for the dedicated Pitcher Exposure table); omit for
 * every player. */
export function buildExposureRows(lineups: Lineup[], playerTypeFilter?: "pitcher" | "hitter"): ExposureRow[] {
  if (lineups.length === 0) return [];

  const counts = new Map<string, { name: string; team: string; playerType: "pitcher" | "hitter"; count: number }>();
  for (const lineup of lineups) {
    for (const a of lineup.assignments) {
      const playerType: "pitcher" | "hitter" = a.slot === "P" ? "pitcher" : "hitter";
      const key = a.dk_player_id;
      const existing = counts.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        counts.set(key, { name: a.name, team: a.team, playerType, count: 1 });
      }
    }
  }

  const rows: ExposureRow[] = [];
  for (const { name, team, playerType, count } of counts.values()) {
    if (playerTypeFilter && playerType !== playerTypeFilter) continue;
    rows.push({ name, team, playerType, lineups: count, exposurePercent: Math.round((100 * count) / lineups.length) });
  }
  return rows.sort((a, b) => b.exposurePercent - a.exposurePercent || a.name.localeCompare(b.name));
}

/** Team stack exposure: how often each team was the lineup's primary
 * stack (Lineup.primary_stack_team, already computed by
 * optimizer/lineup_generator.py -- never re-derived here). */
export function buildStackExposureRows(lineups: Lineup[]): StackExposureRow[] {
  if (lineups.length === 0) return [];

  const counts = new Map<string, number>();
  for (const lineup of lineups) {
    if (!lineup.primary_stack_team) continue;
    counts.set(lineup.primary_stack_team, (counts.get(lineup.primary_stack_team) ?? 0) + 1);
  }

  return Array.from(counts.entries())
    .map(([team, count]) => ({ team, lineups: count, exposurePercent: Math.round((100 * count) / lineups.length) }))
    .sort((a, b) => b.exposurePercent - a.exposurePercent || a.team.localeCompare(b.team));
}
