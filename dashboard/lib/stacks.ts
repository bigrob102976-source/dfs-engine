import type { PlayerRow, TeamPopularity } from "./types";

export interface StackSummary {
  team: string;
  averageProjection: number | null;
  averageOwnership: number | null;
  teamPopularityScore: number | null;
  averagePower: number | null;
  averageConfidence: number | null;
  confirmedHitterCount: number;
  // Milestone 27.2: `confirmedHitterCount` is exactly what its name
  // says (lineupStatus === "active") -- separate from this, since a
  // team's real DK hitters are now always preserved even before their
  // lineup posts (see lib/normalize.ts's own Milestone 27.2 docstring).
  totalHitterCount: number;
  top5: PlayerRow[];
}

function avg(values: number[]): number | null {
  if (values.length === 0) return null;
  return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 100) / 100;
}

/** Summarizes existing hitter data by team -- no simulation, just
 * aggregation of what the Batter Agent and Ownership Model already
 * produced for this slate. */
export function buildStackSummaries(
  hitterRows: PlayerRow[],
  teamPopularity: Record<string, TeamPopularity>,
): StackSummary[] {
  const byTeam = new Map<string, PlayerRow[]>();
  for (const row of hitterRows) {
    const list = byTeam.get(row.team) ?? [];
    list.push(row);
    byTeam.set(row.team, list);
  }

  const summaries: StackSummary[] = [];
  for (const [team, rows] of byTeam) {
    const projections = rows.map((r) => r.projection).filter((v): v is number => v !== null);
    const ownerships = rows.map((r) => r.ownership).filter((v): v is number => v !== null);
    const powers = rows.map((r) => r.power).filter((v): v is number => v !== null);
    const confidences = rows.map((r) => r.confidence).filter((v): v is number => v !== null);
    // Milestone 27.2: ranked by projection first (existing behavior,
    // unchanged for any row that HAS one), falling back to salary as the
    // tiebreak -- so a team with no projections yet (e.g. lineup not
    // posted) still shows its real, highest-salaried DK players instead
    // of an empty card, never a fabricated projection.
    const top5 = [...rows]
      .sort((a, b) => {
        const proj = (b.projection ?? -1) - (a.projection ?? -1);
        if (proj !== 0) return proj;
        return (b.salary ?? -1) - (a.salary ?? -1);
      })
      .slice(0, 5);

    summaries.push({
      team,
      averageProjection: avg(projections),
      averageOwnership: avg(ownerships),
      teamPopularityScore: teamPopularity[team]?.team_popularity_score ?? null,
      averagePower: avg(powers),
      averageConfidence: avg(confidences),
      confirmedHitterCount: rows.filter((r) => r.lineupStatus === "active").length,
      totalHitterCount: rows.length,
      top5,
    });
  }

  return summaries.sort((a, b) => (b.averageProjection ?? -Infinity) - (a.averageProjection ?? -Infinity));
}
