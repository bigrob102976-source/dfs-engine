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

  // Milestone 32.3B: only ever populated on a merged (pitcher+hitter)
  // "BIG MONEY ML" map -- see getMlProjectionByPlayerId below. A raw
  // pitcher-only snapshot read via loadLatestMlProjectionSnapshot never
  // carries these; both are always null/undefined for pitcher rows.
  batting_order?: number | null;
  player_type?: "pitcher" | "hitter";
}

// Milestone 32.3B: Big Money ML SHADOW hitter projections. A SIBLING of
// MlPitcherProjection (same canonical "BIG MONEY ML" source, hitter-
// specific batting_order field added) -- read from a separate
// ml_hitter_projection_*.json snapshot stream sharing the same
// ml_projection_snapshots/<date>/ root (see big_money_ml/persistence.py).
export interface MlHitterProjection {
  player_id: string;
  dk_player_id: string | null;
  name: string;
  team: string;
  opponent: string;
  game_id: string | null;
  salary: number | null;
  batting_order: number | null;

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

// Milestone 32.3B: hitter equivalent of MlProjectionDocument, read from
// the ml_hitter_projection_*.json snapshot stream.
export interface MlHitterProjectionDocument {
  slate_date: string;
  generated_at: string;
  model_version: string;
  warehouse_version: string;

  raw_dk_hitter_count: number;
  confirmed_starting_hitter_count: number;
  ml_eligible_hitter_count: number;
  ml_projections_generated: number;
  ml_projections_missing: number;

  feature_parity_summary: MlFeatureParitySummary;
  players: MlHitterProjection[];
  warnings: string[];
}

/** Reads the latest immutable Big Money ML PITCHER shadow snapshot for
 * `date`, if any. Pure filesystem read -- never triggers generation
 * (see scripts/run_ml_shadow_inference.py for that). */
export async function loadLatestMlProjectionSnapshot(date: string): Promise<MlProjectionDocument | null> {
  const dir = artifactPath(ARTIFACT_DIRS.mlProjectionSnapshots, date);
  const path = await findLatestFile(dir, "ml_projection_");
  return safeReadJson<MlProjectionDocument>(path);
}

/** Reads the latest immutable Big Money ML HITTER shadow snapshot for
 * `date`, if any. Pure filesystem read -- never triggers generation
 * (see scripts/run_ml_hitter_shadow_inference.py for that). Filename
 * prefix "ml_hitter_projection_" never collides with the pitcher
 * stream's "ml_projection_" prefix despite sharing the same date folder. */
export async function loadLatestMlHitterProjectionSnapshot(date: string): Promise<MlHitterProjectionDocument | null> {
  const dir = artifactPath(ARTIFACT_DIRS.mlProjectionSnapshots, date);
  const path = await findLatestFile(dir, "ml_hitter_projection_");
  return safeReadJson<MlHitterProjectionDocument>(path);
}

/** { player_id -> MlPitcherProjection } map from the latest Big Money
 * ML PITCHER-only snapshot for `date`. Returns an empty map (never
 * null/throws) when no snapshot exists yet. Prefer
 * getMlProjectionByPlayerId below for the unified "BIG MONEY ML" view
 * (pitchers + hitters merged) -- this pitcher-only variant is kept for
 * callers that genuinely only care about pitchers. */
export async function getMlPitcherProjectionByPlayerId(date: string): Promise<Map<string, MlPitcherProjection>> {
  const snapshot = await loadLatestMlProjectionSnapshot(date);
  const map = new Map<string, MlPitcherProjection>();
  if (!snapshot) return map;
  for (const p of snapshot.players) {
    map.set(p.player_id, { ...p, player_type: "pitcher", batting_order: null });
  }
  return map;
}

/** { player_id -> MlHitterProjection } map from the latest Big Money ML
 * HITTER-only snapshot for `date`. Returns an empty map (never
 * null/throws) when no snapshot exists yet. */
export async function getMlHitterProjectionByPlayerId(date: string): Promise<Map<string, MlHitterProjection>> {
  const snapshot = await loadLatestMlHitterProjectionSnapshot(date);
  const map = new Map<string, MlHitterProjection>();
  if (!snapshot) return map;
  for (const p of snapshot.players) {
    map.set(p.player_id, p);
  }
  return map;
}

/** Milestone 32.3B: the ONE unified "BIG MONEY ML" map the UI actually
 * consumes -- { player_id -> projection } merged across BOTH the
 * pitcher and hitter shadow-inference snapshot streams for `date`.
 * mlb_player_id spaces never collide between pitchers and hitters (a
 * given MLBAM id is one specific person), so a plain merge is safe.
 * Every entry is stamped with player_type so a caller can distinguish
 * a pitcher's row from a hitter's row without a second lookup; hitter
 * rows carry their real batting_order, pitcher rows always carry null. */
export async function getMlProjectionByPlayerId(date: string): Promise<Map<string, MlPitcherProjection>> {
  const [map, hitterMap] = await Promise.all([getMlPitcherProjectionByPlayerId(date), getMlHitterProjectionByPlayerId(date)]);
  for (const [playerId, p] of hitterMap) {
    map.set(playerId, { ...p, player_type: "hitter" });
  }
  return map;
}

export interface BigMoneyMlProvenance {
  pitcherModelVersion: string | null;
  hitterModelVersion: string | null;
  pitcherSnapshotGeneratedAt: string | null;
  hitterSnapshotGeneratedAt: string | null;
}

/** Milestone 32.4: provenance metadata for a lineup built with Big
 * Money ML as the projection source -- read from the latest persisted
 * snapshot of each stream (never invented, never defaulted to "current
 * time"). All null when no snapshot exists yet for that player type. */
export async function getBigMoneyMlProvenance(date: string): Promise<BigMoneyMlProvenance> {
  const [pitcherDoc, hitterDoc] = await Promise.all([loadLatestMlProjectionSnapshot(date), loadLatestMlHitterProjectionSnapshot(date)]);
  return {
    pitcherModelVersion: pitcherDoc?.model_version ?? null,
    hitterModelVersion: hitterDoc?.model_version ?? null,
    pitcherSnapshotGeneratedAt: pitcherDoc?.generated_at ?? null,
    hitterSnapshotGeneratedAt: hitterDoc?.generated_at ?? null,
  };
}
