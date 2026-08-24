// Milestone 20: AI Projection Engine. Pure, read-only loaders for the
// immutable ai_projection_snapshots/<date>/ai_projection_*.json artifact
// (projection_engine/scoring.py's output) -- never recomputes a signal,
// never triggers generation (see scripts/run_ai_projection_engine.py for
// that). Mirrors lib/externalProjections.ts's loader shape exactly.

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeReadJson } from "./discovery";

export interface AiSignalContribution {
  category: string;
  label: string;
  raw_delta: number;
  weight: number;
  delta: number;
  reason: string;
}

export interface AiPlayerProjection {
  player_id: string;
  name: string;
  team: string;
  player_type: "pitcher" | "hitter";
  opponent: string | null;
  game_id: string | null;
  salary: number | null;

  independent_projection: number | null;
  independent_ceiling: number | null;
  independent_floor: number | null;
  external_projection: number | null;
  adjusted_projection: number | null;

  ai_projection: number | null;
  ai_ceiling: number | null;
  ai_floor: number | null;
  ai_confidence: number | null;
  ai_risk: number | null;
  ai_grade: string | null;
  ai_value_score: number | null;

  total_adjustment: number;
  total_adjustment_percent: number | null;
  adjustment_capped: boolean;

  signals: AiSignalContribution[];
  reasons: string[];
  ai_summary: string;
  model_version: string;
}

export interface AiProjectionSnapshot {
  slate_date: string;
  generated_at: string;
  model_version: string;
  pitcher_snapshot_path: string | null;
  batter_snapshot_path: string | null;
  player_count: number;
  players: AiPlayerProjection[];
  warnings: string[];
  environment_report_present?: boolean;
  ownership_snapshot_present?: boolean;
  adjusted_snapshot_present?: boolean;
  dfs_pool_present?: boolean;
}

/** Reads the latest immutable AI Projection snapshot for `date`, if any.
 * Pure filesystem read -- never triggers generation (see
 * scripts/run_ai_projection_engine.py for that). */
export async function loadLatestAiProjectionSnapshot(date: string): Promise<AiProjectionSnapshot | null> {
  const dir = artifactPath(ARTIFACT_DIRS.aiProjectionSnapshots, date);
  const path = await findLatestFile(dir, "ai_projection_");
  return safeReadJson<AiProjectionSnapshot>(path);
}

/** { player_id -> AiPlayerProjection } map from the latest AI Projection
 * snapshot for `date`. Returns an empty map (never null/throws) when no
 * snapshot exists yet, so callers can join against it unconditionally. */
export async function getAiProjectionByPlayerId(date: string): Promise<Map<string, AiPlayerProjection>> {
  const snapshot = await loadLatestAiProjectionSnapshot(date);
  const map = new Map<string, AiPlayerProjection>();
  if (!snapshot) return map;
  for (const p of snapshot.players) {
    map.set(p.player_id, p);
  }
  return map;
}
