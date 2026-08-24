import { listAllKnownSlateDates, loadLatestOwnershipEvaluation, loadLatestPitcherEvaluation } from "./loaders";
import type { JsonRecord } from "./types";

export interface TrendDelta {
  pitcherMaeDelta: number | null; // negative = improved (lower MAE than prior slate)
  ownershipMaeDelta: number | null;
}

export interface YesterdaySummary {
  date: string | null;
  priorDate: string | null;
  pitcherMae: number | null;
  ownershipMae: number | null;
  projectionCorrelation: number | null;
  ownershipCorrelation: number | null;
  topProjectionMiss: JsonRecord | null;
  worstOwnershipMiss: JsonRecord | null;
  bestLeverageCall: JsonRecord | null;
  worstChalkMiss: JsonRecord | null;
  trend: TrendDelta | null;
}

function biggerAbsError(records: JsonRecord[] | undefined, errorKey: string): JsonRecord | null {
  if (!records || records.length === 0) return null;
  return [...records].sort((a, b) => Math.abs((b[errorKey] as number) ?? 0) - Math.abs((a[errorKey] as number) ?? 0))[0] ?? null;
}

/** The most recent slate date that has ANY evaluation on disk (pitcher
 * or ownership) -- "yesterday" in the sense of "the last slate we
 * actually graded", not necessarily the calendar date before today. */
export async function findLatestEvaluatedDate(): Promise<string | null> {
  for (const date of await listAllKnownSlateDates()) {
    const [pitcherEval, ownershipEval] = await Promise.all([loadLatestPitcherEvaluation(date), loadLatestOwnershipEvaluation(date)]);
    if (pitcherEval.data || ownershipEval.data) return date;
  }
  return null;
}

export async function buildYesterdaySummary(): Promise<YesterdaySummary> {
  const date = await findLatestEvaluatedDate();
  if (!date) {
    return {
      date: null, priorDate: null, pitcherMae: null, ownershipMae: null, projectionCorrelation: null,
      ownershipCorrelation: null, topProjectionMiss: null, worstOwnershipMiss: null, bestLeverageCall: null,
      worstChalkMiss: null, trend: null,
    };
  }

  const [pitcherEvalLoaded, ownershipEvalLoaded] = await Promise.all([loadLatestPitcherEvaluation(date), loadLatestOwnershipEvaluation(date)]);
  const pitcherEval = pitcherEvalLoaded.data;
  const ownershipEval = ownershipEvalLoaded.data;

  const topProjectionMiss = biggerAbsError(
    [...(pitcherEval?.biggest_busts ?? []), ...(pitcherEval?.biggest_positive_surprises ?? [])],
    "error",
  );
  const worstOwnershipMiss = biggerAbsError(
    [...(ownershipEval?.biggest_over_projections ?? []), ...(ownershipEval?.biggest_under_projections ?? [])],
    "error",
  );

  const leverageTag = (ownershipEval?.tag_performance ?? []).find(
    (t) => t.tag === "positive_leverage" || t.tag === "elite_leverage",
  );
  const chalkTag = (ownershipEval?.tag_performance ?? []).find((t) => t.tag === "chalk");

  // Find prior evaluated date (strictly before `date`) for trend arrows.
  const allDates = await listAllKnownSlateDates();
  let priorDate: string | null = null;
  for (const d of allDates.filter((d) => d < date)) {
    const [priorPitcherEval, priorOwnershipEval] = await Promise.all([loadLatestPitcherEvaluation(d), loadLatestOwnershipEvaluation(d)]);
    if (priorPitcherEval.data || priorOwnershipEval.data) {
      priorDate = d;
      break;
    }
  }

  let trend: TrendDelta | null = null;
  if (priorDate) {
    const [priorPitcherLoaded, priorOwnershipLoaded] = await Promise.all([
      loadLatestPitcherEvaluation(priorDate),
      loadLatestOwnershipEvaluation(priorDate),
    ]);
    const priorPitcher = priorPitcherLoaded.data;
    const priorOwnership = priorOwnershipLoaded.data;
    const curPitcherMae = pitcherEval?.slate_metrics?.mae ?? null;
    const priorPitcherMae = priorPitcher?.slate_metrics?.mae ?? null;
    const curOwnershipMae = ownershipEval?.overall_metrics?.mae ?? null;
    const priorOwnershipMae = priorOwnership?.overall_metrics?.mae ?? null;
    trend = {
      pitcherMaeDelta: curPitcherMae !== null && priorPitcherMae !== null ? Math.round((curPitcherMae - priorPitcherMae) * 1000) / 1000 : null,
      ownershipMaeDelta: curOwnershipMae !== null && priorOwnershipMae !== null ? Math.round((curOwnershipMae - priorOwnershipMae) * 1000) / 1000 : null,
    };
  }

  return {
    date,
    priorDate,
    pitcherMae: pitcherEval?.slate_metrics?.mae ?? null,
    ownershipMae: ownershipEval?.overall_metrics?.mae ?? null,
    projectionCorrelation: pitcherEval?.slate_metrics?.projection_correlation ?? null,
    ownershipCorrelation: ownershipEval?.overall_metrics?.correlation ?? null,
    topProjectionMiss,
    worstOwnershipMiss,
    bestLeverageCall: (leverageTag as unknown as JsonRecord) ?? null,
    worstChalkMiss: (chalkTag as unknown as JsonRecord) ?? null,
    trend,
  };
}
