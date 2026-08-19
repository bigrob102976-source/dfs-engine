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
  // says (optimizerEligible, i.e. STARTING_HITTER -- see Milestone 30.1
  // below) -- separate from this, since a team's real DK hitters are now
  // always preserved even before their lineup posts (see
  // lib/normalize.ts's own Milestone 27.2 docstring).
  totalHitterCount: number;
  // Milestone 30.1: "WAITING_FOR_LINEUP" when this team has zero
  // confirmed starting hitters yet (lineup not posted) -- "CONFIRMED"
  // once at least one is posted. Every metric below (averages, top5) is
  // computed from confirmed starters ONLY -- never diluted by bench
  // players, and never fabricated from unconfirmed ones while waiting.
  status: "CONFIRMED" | "WAITING_FOR_LINEUP";
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
    // Milestone 30.1: stacks reflect confirmed starting lineups only --
    // bench/unconfirmed hitters are preserved in `rows`/totalHitterCount
    // for visibility, but never feed a stack's averages or top5.
    const confirmedRows = rows.filter((r) => r.optimizerEligible);
    const projections = confirmedRows.map((r) => r.projection).filter((v): v is number => v !== null);
    const ownerships = confirmedRows.map((r) => r.ownership).filter((v): v is number => v !== null);
    const powers = confirmedRows.map((r) => r.power).filter((v): v is number => v !== null);
    const confidences = confirmedRows.map((r) => r.confidence).filter((v): v is number => v !== null);
    // Ranked by projection first (existing behavior, unchanged for any
    // confirmed row that HAS one), falling back to salary as the
    // tiebreak. Never falls back to bench/unconfirmed rows -- a team
    // with zero confirmed starters yet gets an empty top5 and
    // status="WAITING_FOR_LINEUP", not a fabricated stack.
    const top5 = [...confirmedRows]
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
      confirmedHitterCount: confirmedRows.length,
      totalHitterCount: rows.length,
      status: confirmedRows.length > 0 ? "CONFIRMED" : "WAITING_FOR_LINEUP",
      top5,
    });
  }

  return summaries.sort((a, b) => (b.averageProjection ?? -Infinity) - (a.averageProjection ?? -Infinity));
}
