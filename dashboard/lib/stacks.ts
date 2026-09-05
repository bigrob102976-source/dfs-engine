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

// ---------------------------------------------------------------------------
// MLB DASHBOARD INTELLIGENCE: Top Stacks / Best Value Stack. Built ONLY on
// top of StackSummary.top5 (already the best-projected optimizer-eligible
// hitters for the team, confirmed/probable only, never bench/out/scratched
// -- see buildStackSummaries above) -- never a second team-grouping or
// hitter-selection algorithm. A "candidate" is the real N-man combination
// (default 5, DK MLB's own primary stack size) actually usable right now;
// its size honestly reflects however many eligible hitters the team has
// (e.g. 3 when only 3 are confirmed/probable) rather than fabricating
// placeholder players to reach N.
// ---------------------------------------------------------------------------

export interface StackCandidate {
  team: string;
  requestedSize: number;
  stackSize: number; // hitters.length -- may be < requestedSize if the team doesn't have that many eligible hitters
  hitters: PlayerRow[];
  totalSalary: number | null; // null unless every included hitter has a real salary
  totalProjection: number | null; // null unless every included hitter has a real projection
  totalCeiling: number | null; // sum of whichever hitters have a real ceiling (never fabricated for the rest)
  averageOwnership: number | null;
  averageLeverage: number | null;
  eligibleHitterCount: number; // StackSummary.confirmedHitterCount -- ALL eligible hitters on the team, not just the ones in `hitters`
  status: "CONFIRMED" | "WAITING_FOR_LINEUP";
  /** points per $1,000 of totalSalary -- same "value" convention as
   * commandCenter.ts::valueScore, applied to the whole stack instead of
   * one player. Computed from this candidate's OWN totals (not
   * commandCenter.ts::rankStacksByValue's mixed all-confirmed-average /
   * top5-average denominator), so numerator and denominator always
   * describe the exact same set of hitters. */
  value: number | null;
}

function sumIfComplete(values: Array<number | null>): number | null {
  if (values.length === 0) return null;
  const present = values.filter((v): v is number => v !== null);
  return present.length === values.length ? Math.round(present.reduce((a, b) => a + b, 0) * 100) / 100 : null;
}
function sumAvailable(values: Array<number | null>): number | null {
  const present = values.filter((v): v is number => v !== null);
  return present.length === 0 ? null : Math.round(present.reduce((a, b) => a + b, 0) * 100) / 100;
}

/** Builds a real, usable N-man (default 5, DK MLB's own primary stack
 * size -- Phase 5) stack candidate per team from each StackSummary's
 * already-selected top5 -- a 4-man/3-man view (Phase 5) is just a
 * cheaper re-slice of the SAME array, never a new selection pass. Teams
 * with zero eligible hitters are dropped entirely (never a fabricated
 * empty "stack"); a team with 1 eligible hitter is kept (stackSize
 * reflects reality) but excluded downstream by the ranking functions'
 * own minimum-size floor. */
export function buildStackCandidates(stacks: StackSummary[], size = 5): StackCandidate[] {
  return stacks
    .filter((s) => s.top5.length > 0)
    .map((s) => {
      const hitters = s.top5.slice(0, size);
      const totalSalary = sumIfComplete(hitters.map((h) => h.salary));
      const totalProjection = sumIfComplete(hitters.map((h) => h.projection));
      const totalCeiling = sumAvailable(hitters.map((h) => h.ceiling));
      const ownerships = hitters.map((h) => h.ownership).filter((v): v is number => v !== null);
      const leverages = hitters.map((h) => h.leverage).filter((v): v is number => v !== null);
      const averageOwnership = ownerships.length ? Math.round((ownerships.reduce((a, b) => a + b, 0) / ownerships.length) * 100) / 100 : null;
      const averageLeverage = leverages.length ? Math.round((leverages.reduce((a, b) => a + b, 0) / leverages.length) * 100) / 100 : null;
      const value = totalProjection !== null && totalSalary ? Math.round((totalProjection / totalSalary) * 1000 * 100) / 100 : null;
      return {
        team: s.team,
        requestedSize: size,
        stackSize: hitters.length,
        hitters,
        totalSalary,
        totalProjection,
        totalCeiling,
        averageOwnership,
        averageLeverage,
        eligibleHitterCount: s.confirmedHitterCount,
        status: s.status,
        value,
      };
    });
}

/** A real stack (Phase 3/13: "not enough eligible hitters" is honestly
 * distinct from "no stacks at all") needs at least 2 hitters -- a
 * 1-player "stack" isn't a stack in DFS terms. */
const MINIMUM_STACK_SIZE = 2;

/** "Big Money Stack Score" -- documented here in full (Phase 4): rewards
 * projected production AND ceiling equally (their average, so neither
 * alone can dominate), plus two small, bounded secondary bonuses: usable
 * lineup depth (extra real eligible hitters beyond the requested stack
 * size -- a more resilient stack if a player gets scratched) and value
 * (points per $1k) -- deliberately NOT ownership/leverage, per this
 * milestone's explicit "do NOT make low ownership automatically better
 * than actual projection quality" rule; ownership/leverage stay
 * display-only fields (Phase 8), never a ranking input here. Both bonus
 * terms are small relative to the primary production/ceiling average
 * (typically 25-55 for a real 5-man MLB stack) so they can only ever
 * break near-ties, never override real production quality. */
export function stackScore(candidate: StackCandidate): number | null {
  if (candidate.totalProjection === null || candidate.totalCeiling === null) return null;
  const productionCeilingAverage = (candidate.totalProjection + candidate.totalCeiling) / 2;
  const depthBonus = Math.max(0, candidate.eligibleHitterCount - candidate.stackSize) * 0.5;
  const valueBonus = candidate.value !== null ? candidate.value * 2 : 0;
  return Math.round((productionCeilingAverage + depthBonus + valueBonus) * 100) / 100;
}

export interface ScoredStackCandidate extends StackCandidate {
  score: number;
}

/** Ranks real stack candidates (>= MINIMUM_STACK_SIZE hitters) by the Big
 * Money Stack Score -- this is what powers the "Top Stacks" list (Phase
 * 4). A candidate stackScore() can't compute for (missing totals) is
 * excluded, never ranked with a fabricated/zero score. */
export function rankStackCandidatesByScore(candidates: StackCandidate[]): ScoredStackCandidate[] {
  return candidates
    .filter((c) => c.stackSize >= MINIMUM_STACK_SIZE)
    .map((c) => ({ ...c, score: stackScore(c) }))
    .filter((c): c is ScoredStackCandidate => c.score !== null)
    .sort((a, b) => b.score - a.score);
}

/** Ranks real stack candidates by DFS value (points per $1k) -- this is
 * "Best Value Stack" (Phase 6): NOT necessarily the #1 scored stack,
 * just whichever real, usable stack gives the strongest production per
 * dollar. */
export function rankStackCandidatesByValue(candidates: StackCandidate[]): StackCandidate[] {
  return candidates
    .filter((c) => c.stackSize >= MINIMUM_STACK_SIZE && c.value !== null)
    .sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
}
