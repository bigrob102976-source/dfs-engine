import type { PlayerRow, TeamPopularity } from "./types";

export interface StackSummary {
  team: string;
  averageProjection: number | null;
  averageOwnership: number | null;
  teamPopularityScore: number | null;
  averagePower: number | null;
  averageConfidence: number | null;
  confirmedHitterCount: number;
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
    const top5 = [...rows]
      .filter((r) => r.projection !== null)
      .sort((a, b) => (b.projection ?? 0) - (a.projection ?? 0))
      .slice(0, 5);

    summaries.push({
      team,
      averageProjection: avg(projections),
      averageOwnership: avg(ownerships),
      teamPopularityScore: teamPopularity[team]?.team_popularity_score ?? null,
      averagePower: avg(powers),
      averageConfidence: avg(confidences),
      confirmedHitterCount: rows.length,
      top5,
    });
  }

  return summaries.sort((a, b) => (b.averageProjection ?? -Infinity) - (a.averageProjection ?? -Infinity));
}
