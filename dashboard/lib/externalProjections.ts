import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeReadJson } from "./discovery";

export interface ExternalProjectionPlayer {
  external_player_id: string;
  name: string;
  team: string;
  position: string;
  projection: number;
  provider_name: string;
  updated_at: string;
  slate_id: string;
  opponent: string | null;
  salary: number | null;
  ceiling: number | null;
  floor: number | null;
  ownership_projection: number | null;
  slate_name: string | null;
  provider_version: string | null;
}

export interface ExternalBaselineSnapshot {
  slate_date: string;
  provider: string;
  provider_name: string;
  provider_version: string | null;
  is_mock: boolean;
  slate_id: string;
  slate_name: string | null;
  retrieved_at: string;
  player_count: number;
  players: ExternalProjectionPlayer[];
  warnings: string[];
}

export interface AdjustmentFactor {
  factor: string;
  delta: number;
  reason: string;
  confidence: number | null;
}

export interface PlayerProjectionRecord {
  independent_player_id: string;
  name: string;
  team: string;
  player_type: "pitcher" | "hitter";
  external_player_id: string | null;
  external_projection: number | null;
  external_ceiling: number | null;
  external_floor: number | null;
  external_provider: string | null;
  external_provider_timestamp: string | null;
  independent_projection: number | null;
  independent_ceiling: number | null;
  independent_floor: number | null;
  adjusted_projection: number | null;
  adjusted_ceiling: number | null;
  adjusted_floor: number | null;
  adjustment_delta: number | null;
  adjustment_percent: number | null;
  adjustment_confidence: number | null;
  adjustment_reasons: string[];
  adjustments: AdjustmentFactor[];
}

export interface AdjustedProjectionSnapshot {
  slate_date: string;
  generated_at: string;
  adjustment_model_version: string;
  baseline_provider: string | null;
  baseline_provider_name: string | null;
  baseline_is_mock: boolean | null;
  baseline_retrieved_at: string | null;
  pitcher_snapshot_path: string | null;
  batter_snapshot_path: string | null;
  record_count: number;
  records: PlayerProjectionRecord[];
  unmatched_external: string[];
  unmatched_independent: string[];
  ambiguous_external: string[];
}

/** Reads the latest immutable external-projection baseline snapshot for
 * `date`, if any. Pure filesystem read -- never triggers generation
 * (see scripts/build_external_projection_baseline.py for that). */
export async function loadLatestBaselineSnapshot(date: string): Promise<ExternalBaselineSnapshot | null> {
  const dir = artifactPath(ARTIFACT_DIRS.externalProjectionSnapshots, date);
  const path = await findLatestFile(dir, "provider_");
  return safeReadJson<ExternalBaselineSnapshot>(path);
}

/** Reads the latest immutable Big Money adjusted-projection snapshot
 * for `date`, if any. Pure filesystem read -- never triggers generation
 * (see scripts/run_projection_adjustment.py for that). */
export async function loadLatestAdjustedSnapshot(date: string): Promise<AdjustedProjectionSnapshot | null> {
  const dir = artifactPath(ARTIFACT_DIRS.adjustedProjectionSnapshots, date);
  const path = await findLatestFile(dir, "adjusted_");
  return safeReadJson<AdjustedProjectionSnapshot>(path);
}

export interface ProjectionComparisonRow {
  independentProjection: number | null;
  externalProjection: number | null;
  adjustedProjection: number | null;
  adjustmentDelta: number | null;
  adjustmentPercent: number | null;
  adjustmentReasons: string[];
}

/** Builds a { mlb_player_id -> comparison row } map from the latest
 * adjusted snapshot for `date` (which already carries independent +
 * external + adjusted values per player -- see
 * external_projections/models.py's PlayerProjectionRecord). Returns an
 * empty map (never null/throws) when no adjusted snapshot exists yet,
 * so callers can join against it unconditionally. */
export async function getProjectionComparisonByPlayerId(date: string): Promise<Map<string, ProjectionComparisonRow>> {
  const snapshot = await loadLatestAdjustedSnapshot(date);
  const map = new Map<string, ProjectionComparisonRow>();
  if (!snapshot) return map;

  for (const r of snapshot.records) {
    map.set(r.independent_player_id, {
      independentProjection: r.independent_projection,
      externalProjection: r.external_projection,
      adjustedProjection: r.adjusted_projection,
      adjustmentDelta: r.adjustment_delta,
      adjustmentPercent: r.adjustment_percent,
      adjustmentReasons: r.adjustment_reasons,
    });
  }
  return map;
}
