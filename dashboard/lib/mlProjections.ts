// Milestone 32.2B: Big Money ML SHADOW pitcher projections. Pure,
// read-only loaders for the immutable ml_projection_snapshots/<date>/
// ml_projection_*.json artifact (big_money_ml/persistence.py's output)
// -- never recomputes a projection, never triggers generation (see
// scripts/run_ml_shadow_inference.py for that). Mirrors
// lib/nativeProjections.ts's loader shape exactly, field-for-field with
// big_money_ml/models.py's dataclasses.
//
// SHADOW MODE: nothing in this file is wired into the optimizer's
// ProjectionSource -- see lib/optimizerWorkspace/types.ts, which never
// lists "big_money_ml" as a selectable value.

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeReadJson } from "./discovery";

export type MlProjectionStatus = "LIVE_PREGAME" | "PREGAME_FROZEN" | "MISSING" | "INVALID_FEATURE_PARITY";

export interface MlPitcherProjection {
  player_id: string;
  dk_player_id: string | null;
  name: string;
  team: string;
  opponent: string;
  game_id: string | null;
  salary: number | null;

  projection: number | null;
  model_version: string;
  data_quality_score: number | null;
  feature_coverage: number | null;
  missing_features: string[];

  projection_status: MlProjectionStatus;
  feature_timestamp: string | null;
  game_scheduled_start_utc: string | null;

  warnings: string[];
}

export interface MlFeatureParitySummary {
  total_expected_features: number;
  exact_count: number;
  compatible_count: number;
  missing_count: number;
  incompatible_count: number;
  missing_features: string[];
  incompatible_features: string[];
}

export interface MlProjectionDocument {
  slate_date: string;
  generated_at: string;
  model_version: string;
  warehouse_version: string;

  raw_dk_pitcher_count: number;
  starting_pitcher_count: number;
  ml_eligible_pitcher_count: number;
  ml_projections_generated: number;
  ml_projections_missing: number;

  feature_parity_summary: MlFeatureParitySummary;
  players: MlPitcherProjection[];
  warnings: string[];
}

/** Reads the latest immutable Big Money ML shadow snapshot for `date`,
 * if any. Pure filesystem read -- never triggers generation (see
 * scripts/run_ml_shadow_inference.py for that). */
export function loadLatestMlProjectionSnapshot(date: string): MlProjectionDocument | null {
  const dir = artifactPath(ARTIFACT_DIRS.mlProjectionSnapshots, date);
  const path = findLatestFile(dir, "ml_projection_");
  return safeReadJson<MlProjectionDocument>(path);
}

/** { player_id -> MlPitcherProjection } map from the latest Big Money
 * ML snapshot for `date`. Returns an empty map (never null/throws) when
 * no snapshot exists yet, so callers can join against it unconditionally. */
export function getMlProjectionByPlayerId(date: string): Map<string, MlPitcherProjection> {
  const snapshot = loadLatestMlProjectionSnapshot(date);
  const map = new Map<string, MlPitcherProjection>();
  if (!snapshot) return map;
  for (const p of snapshot.players) {
    map.set(p.player_id, p);
  }
  return map;
}
