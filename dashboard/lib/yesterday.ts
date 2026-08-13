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
export function findLatestEvaluatedDate(): string | null {
  for (const date of listAllKnownSlateDates()) {
    if (loadLatestPitcherEvaluation(date).data || loadLatestOwnershipEvaluation(date).data) return date;
  }
  return null;
}

export function buildYesterdaySummary(): YesterdaySummary {
  const date = findLatestEvaluatedDate();
  if (!date) {
    return {
      date: null, priorDate: null, pitcherMae: null, ownershipMae: null, projectionCorrelation: null,
      ownershipCorrelation: null, topProjectionMiss: null, worstOwnershipMiss: null, bestLeverageCall: null,
      worstChalkMiss: null, trend: null,
    };
  }

  const pitcherEval = loadLatestPitcherEvaluation(date).data;
  const ownershipEval = loadLatestOwnershipEvaluation(date).data;

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
  const allDates = listAllKnownSlateDates();
  const priorDate = allDates.filter((d) => d < date).find((d) => loadLatestPitcherEvaluation(d).data || loadLatestOwnershipEvaluation(d).data) ?? null;

  let trend: TrendDelta | null = null;
  if (priorDate) {
    const priorPitcher = loadLatestPitcherEvaluation(priorDate).data;
    const priorOwnership = loadLatestOwnershipEvaluation(priorDate).data;
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
