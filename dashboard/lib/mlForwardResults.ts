// Milestone 32.5: Big Money ML forward RESULTS + LINEUP GRADING. Pure,
// read-only loader for the immutable ml_forward_results/<date>/
// <slate_id>/ml_forward_results_*.json documents (evaluation/
// ml_forward_persistence.py's output) -- never recomputes a grade,
// never triggers collection (see /api/admin/ml-forward-results/collect
// for that, which shells out to scripts/collect_ml_forward_results.py).
//
// SERVER-ONLY (touches node:fs/node:path via artifactRoot.ts/
// discovery.ts) -- a "use client" component must import types and pure
// helpers (pivotModelDisagreements) from ./mlForwardResultsTypes
// instead, never from this file, or the client bundle fails to build.

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeListDir, safeReadJson } from "./discovery";
import type { MlForwardResultsDocument } from "./mlForwardResultsTypes";

export type {
  MlCeilingMonitor,
  MlCeilingThreshold,
  MlDisasterPitcherMonitor,
  MlForwardGameStatus,
  MlForwardResultsDocument,
  MlGradedLineup,
  MlLineupGrading,
  MlLineupPlayerGrade,
  MlLineupSourceComparisonEntry,
  MlModelDisagreementRow,
  MlPlayerGradingRecord,
  MlSourceComparison,
  MlSourceMetricsRow,
  MlZeroGameMonitor,
} from "./mlForwardResultsTypes";
export { pivotModelDisagreements } from "./mlForwardResultsTypes";

function slateFolder(date: string, slateId: string): string {
  return artifactPath(ARTIFACT_DIRS.mlForwardResults, date, slateId);
}

/** Reads the latest immutable forward-grading document for one
 * (date, slate_id) pair, if any. Pure filesystem read -- never
 * triggers collection. */
export function loadLatestMlForwardResults(date: string, slateId: string): MlForwardResultsDocument | null {
  const dir = slateFolder(date, slateId);
  const path = findLatestFile(dir, "ml_forward_results_");
  return safeReadJson<MlForwardResultsDocument>(path);
}

/** Every slate_id that has at least one persisted forward-results
 * document for `date`, newest-collected first. */
export function listMlForwardResultsSlateIds(date: string): string[] {
  const dir = artifactPath(ARTIFACT_DIRS.mlForwardResults, date);
  return safeListDir(dir);
}

/** Every date that has at least one persisted forward-results document
 * for ANY slate, newest first -- used to seed the admin page's slate
 * picker with a sensible default (the most recently graded slate). */
export function listMlForwardResultsDates(): string[] {
  const dir = artifactPath(ARTIFACT_DIRS.mlForwardResults);
  return safeListDir(dir)
    .filter((name) => /^\d{4}-\d{2}-\d{2}$/.test(name))
    .sort()
    .reverse();
}
