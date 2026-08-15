// AI Projection Performance: pure, read-only loader for the immutable
// evaluations/<date>/projection_source_comparison_*.json artifact
// (evaluation/projection_source_comparison.py + projection_source_loader.py's
// output) -- never recomputes MAE/RMSE/correlation, never triggers
// generation (see scripts/run_projection_source_comparison.py for that).
// Pitcher-only: results/<date>/pitcher_results.json is the only actual
// -results source this codebase has, so every source's `n` here counts
// pitchers only.

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeReadJson } from "./discovery";

export type ProjectionSourceLabel = "independent" | "external" | "adjusted" | "ai";

export interface ProjectionSourceMetrics {
  source: ProjectionSourceLabel;
  n: number;
  mae: number | null;
  rmse: number | null;
  correlation: number | null;
  rank_correlation: number | null;
  top5_hit_rate: number | null;
  top10_hit_rate: number | null;
}

export interface ProjectionSourceComparisonDocument {
  slate_date: string;
  generated_at: string;
  actual_result_count: number;
  sources_present: ProjectionSourceLabel[];
  metrics: ProjectionSourceMetrics[];
  ai_vs_independent_mae_improvement_percent: number | null;
}

/** Reads the latest immutable projection-source-comparison snapshot for
 * `date`, if any. Pure filesystem read -- never triggers generation
 * (see scripts/run_projection_source_comparison.py for that). Reuses
 * the same "evaluations" artifact directory as pitcher evaluations --
 * both are postgame grading artifacts for the same slate date, just
 * different filename prefixes. */
export function loadLatestProjectionSourceComparison(date: string): ProjectionSourceComparisonDocument | null {
  const dir = artifactPath(ARTIFACT_DIRS.pitcherEvaluations, date);
  const path = findLatestFile(dir, "projection_source_comparison_");
  return safeReadJson<ProjectionSourceComparisonDocument>(path);
}

export function getSourceMetrics(doc: ProjectionSourceComparisonDocument | null, source: ProjectionSourceLabel): ProjectionSourceMetrics | null {
  return doc?.metrics.find((m) => m.source === source) ?? null;
}
