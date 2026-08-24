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
export async function buildHistorySeries(): Promise<HistoryPoint[]> {
  const dates = [...(await listAllKnownSlateDates())].reverse();
  return Promise.all(
    dates.map(async (date) => {
      const [research, pitcherEval, ownershipEval, lineupSet] = await Promise.all([
        loadResearchSlate(date),
        loadLatestPitcherEvaluation(date),
        loadLatestOwnershipEvaluation(date),
        loadLatestLineupSet(date),
      ]);

      return {
        date,
        games: research.data?.counts?.games ?? null,
        pitcherMae: pitcherEval.data?.slate_metrics?.mae ?? null,
        ownershipMae: ownershipEval.data?.overall_metrics?.mae ?? null,
        projectionCorrelation: pitcherEval.data?.slate_metrics?.projection_correlation ?? null,
        ownershipCorrelation: ownershipEval.data?.overall_metrics?.correlation ?? null,
        lineupsGenerated: lineupSet.data?.lineups_generated ?? null,
      };
    }),
  );
}
