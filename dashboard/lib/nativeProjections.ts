// Milestone 23: Native Projection Model. Pure, read-only loaders for the
// immutable native_projection_snapshots/<date>/native_projection_*.json
// artifact (native_projections/*.py's output) -- never recomputes a
// projection, never triggers generation (see
// scripts/run_native_projection_engine.py for that). Mirrors
// lib/aiProjections.ts's loader shape exactly, field-for-field with
// native_projections/models.py's dataclasses.

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeReadJson } from "./discovery";

export interface NativeComponentValue {
  expected_count: number;
  dk_points_per_event: number;
  dk_points: number;
  reason: string | null;
}

export interface NativeHitterOpportunity {
  expected_pa: number;
  pa_confidence: number;
  reasons: string[];
}

export interface NativePitcherOpportunity {
  expected_innings: number;
  expected_batters_faced: number;
  expected_pitch_count: number;
  workload_confidence: number;
  reasons: string[];
}

export interface NativeHitterComponents {
  singles: NativeComponentValue;
  doubles: NativeComponentValue;
  triples: NativeComponentValue;
  home_runs: NativeComponentValue;
  walks: NativeComponentValue;
  hit_by_pitch: NativeComponentValue;
  stolen_bases: NativeComponentValue;
  runs: NativeComponentValue;
  rbi: NativeComponentValue;
  strikeouts_expected: number;
}

export interface NativePitcherComponents {
  innings_pitched: NativeComponentValue;
  strikeouts: NativeComponentValue;
  walks: NativeComponentValue;
  hit_batsmen: NativeComponentValue;
  hits_allowed: NativeComponentValue;
  earned_runs: NativeComponentValue;
  win_probability: number | null;
  win_probability_is_mock: boolean | null;
}

export interface NativeInputCoverage {
  fields_available: number;
  fields_total: number;
  missing_fields: string[];
  fraction: number;
}

export interface NativePlayerProjection {
  player_id: string;
  name: string;
  team: string;
  player_type: "pitcher" | "hitter";
  opponent: string | null;
  game_id: string | null;
  salary: number | null;
  positions: string[];
  batting_order: number | null;

  native_projection: number;
  native_ceiling: number;
  native_floor: number;
  confidence: number;
  variance: number;

  model_version: string;

  hitter_opportunity: NativeHitterOpportunity | null;
  pitcher_opportunity: NativePitcherOpportunity | null;
  hitter_components: NativeHitterComponents | null;
  pitcher_components: NativePitcherComponents | null;

  input_coverage: NativeInputCoverage | null;
  reasons: string[];
  warnings: string[];

  generated_at: string;
  source_pitcher_snapshot_path: string | null;
  source_batter_snapshot_path: string | null;
  source_environment_snapshot_path: string | null;
}

export interface NativeProjectionDocument {
  slate_date: string;
  generated_at: string;
  model_version: string;
  pitcher_snapshot_path: string | null;
  batter_snapshot_path: string | null;
  environment_snapshot_path: string | null;
  player_count: number;
  players: NativePlayerProjection[];
  warnings: string[];
}

/** Reads the latest immutable Native Projection snapshot for `date`, if
 * any. Pure filesystem read -- never triggers generation (see
 * scripts/run_native_projection_engine.py for that). */
export async function loadLatestNativeProjectionSnapshot(date: string): Promise<NativeProjectionDocument | null> {
  const dir = artifactPath(ARTIFACT_DIRS.nativeProjectionSnapshots, date);
  const path = await findLatestFile(dir, "native_projection_");
  return safeReadJson<NativeProjectionDocument>(path);
}

/** { player_id -> NativePlayerProjection } map from the latest Native
 * Projection snapshot for `date`. Returns an empty map (never
 * null/throws) when no snapshot exists yet, so callers can join against
 * it unconditionally. */
export async function getNativeProjectionByPlayerId(date: string): Promise<Map<string, NativePlayerProjection>> {
  const snapshot = await loadLatestNativeProjectionSnapshot(date);
  const map = new Map<string, NativePlayerProjection>();
  if (!snapshot) return map;
  for (const p of snapshot.players) {
    map.set(p.player_id, p);
  }
  return map;
}
