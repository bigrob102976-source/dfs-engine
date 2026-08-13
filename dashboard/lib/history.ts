import {
  listAllKnownSlateDates,
  loadLatestLineupSet,
  loadLatestOwnershipEvaluation,
  loadLatestPitcherEvaluation,
  loadResearchSlate,
} from "./loaders";

export interface HistoryPoint {
  date: string;
  games: number | null;
  pitcherMae: number | null;
  ownershipMae: number | null;
  projectionCorrelation: number | null;
  ownershipCorrelation: number | null;
  lineupsGenerated: number | null;
}

/** One point per known slate date, OLDEST first (chronological, the
 * natural reading order for a trend chart). Every field is independently
 * nullable -- a slate that only has a research package but no evaluation
 * yet still appears, with the ungenerated fields left null rather than
 * dropped or zero-filled. */
export function buildHistorySeries(): HistoryPoint[] {
  const dates = [...listAllKnownSlateDates()].reverse();
  return dates.map((date) => {
    const research = loadResearchSlate(date).data;
    const pitcherEval = loadLatestPitcherEvaluation(date).data;
    const ownershipEval = loadLatestOwnershipEvaluation(date).data;
    const lineupSet = loadLatestLineupSet(date).data;

    return {
      date,
      games: research?.counts?.games ?? null,
      pitcherMae: pitcherEval?.slate_metrics?.mae ?? null,
      ownershipMae: ownershipEval?.overall_metrics?.mae ?? null,
      projectionCorrelation: pitcherEval?.slate_metrics?.projection_correlation ?? null,
      ownershipCorrelation: ownershipEval?.overall_metrics?.correlation ?? null,
      lineupsGenerated: lineupSet?.lineups_generated ?? null,
    };
  });
}
