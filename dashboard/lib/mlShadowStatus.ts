import { loadLatestMlHitterProjectionSnapshot, loadLatestMlProjectionSnapshot } from "./mlProjections";

export interface MlShadowStatus {
  status: "NO_SNAPSHOT" | "NO_ELIGIBLE_PITCHERS" | "READY" | "PARTIAL";
  slate_date: string;
  model_version: string | null;
  starting_pitcher_count: number;
  ml_eligible_pitcher_count: number;
  ml_projections_generated: number;
  ml_projections_missing: number;
  generated_at: string | null;
}

// Milestone 32.3B: hitter equivalent of MlShadowStatus.
export interface MlHitterShadowStatus {
  status: "NO_SNAPSHOT" | "NO_ELIGIBLE_HITTERS" | "READY" | "PARTIAL";
  slate_date: string;
  model_version: string | null;
  confirmed_starting_hitter_count: number;
  ml_eligible_hitter_count: number;
  ml_projections_generated: number;
  ml_projections_missing: number;
  generated_at: string | null;
}

/** Reads Big Money ML's persisted, observable coverage (never triggers
 * generation -- pure read of the latest ml_projection_snapshots/<date>/
 * document, see lib/mlProjections.ts). A live feature-parity/model-load
 * failure during Process/Refresh appears in that run's errors, not here
 * -- this card only reflects the last persisted snapshot (same division
 * of concerns lib/fantasyProsStatus.ts already documents for itself). */
export function getMlShadowStatus(date: string): MlShadowStatus {
  const doc = loadLatestMlProjectionSnapshot(date);
  if (!doc) {
    return {
      status: "NO_SNAPSHOT", slate_date: date, model_version: null, starting_pitcher_count: 0,
      ml_eligible_pitcher_count: 0, ml_projections_generated: 0, ml_projections_missing: 0, generated_at: null,
    };
  }

  const status: MlShadowStatus["status"] =
    doc.ml_eligible_pitcher_count === 0 ? "NO_ELIGIBLE_PITCHERS" : doc.ml_projections_missing === 0 ? "READY" : "PARTIAL";

  return {
    status,
    slate_date: doc.slate_date,
    model_version: doc.model_version,
    starting_pitcher_count: doc.starting_pitcher_count,
    ml_eligible_pitcher_count: doc.ml_eligible_pitcher_count,
    ml_projections_generated: doc.ml_projections_generated,
    ml_projections_missing: doc.ml_projections_missing,
    generated_at: doc.generated_at,
  };
}

/** Hitter equivalent of getMlShadowStatus -- reads the separate
 * ml_hitter_projection_*.json snapshot stream. Same division of
 * concerns: reflects only the last persisted snapshot, never triggers
 * generation, never blocks slate publication. */
export function getMlHitterShadowStatus(date: string): MlHitterShadowStatus {
  const doc = loadLatestMlHitterProjectionSnapshot(date);
  if (!doc) {
    return {
      status: "NO_SNAPSHOT", slate_date: date, model_version: null, confirmed_starting_hitter_count: 0,
      ml_eligible_hitter_count: 0, ml_projections_generated: 0, ml_projections_missing: 0, generated_at: null,
    };
  }

  const status: MlHitterShadowStatus["status"] =
    doc.ml_eligible_hitter_count === 0 ? "NO_ELIGIBLE_HITTERS" : doc.ml_projections_missing === 0 ? "READY" : "PARTIAL";

  return {
    status,
    slate_date: doc.slate_date,
    model_version: doc.model_version,
    confirmed_starting_hitter_count: doc.confirmed_starting_hitter_count,
    ml_eligible_hitter_count: doc.ml_eligible_hitter_count,
    ml_projections_generated: doc.ml_projections_generated,
    ml_projections_missing: doc.ml_projections_missing,
    generated_at: doc.generated_at,
  };
}
