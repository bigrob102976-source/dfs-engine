// FantasyPros integration: pure, read-only loaders for the immutable
// fantasypros_snapshots/<date>/fantasypros_projection_*.json artifact
// (fantasypros/*.py's output) -- never calls the FantasyPros API, never
// triggers generation (see scripts/fetch_fantasypros_projections.py for
// that, invoked only from the admin Process/Refresh pipeline --
// lib/slatePipeline.ts). Mirrors lib/nativeProjections.ts's loader shape
// exactly, field-for-field with fantasypros/models.py's dataclasses.
//
// IMPORTANT MODEL RULE (per this integration's own spec): FantasyPros is
// a COMPARISON + OPTIONAL OPTIMIZER SOURCE only. Nothing here (or
// anywhere else in this integration) feeds a FantasyPros value into Big
// Money Native or Big Money AI's own computation -- see
// native_projections/ and projection_engine/, neither of which import
// this module.

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeReadJson } from "./discovery";

export interface FantasyProsPlayerProjection {
  fantasypros_id: string;
  name: string;
  team: string;
  player_type: "pitcher" | "hitter";

  yahoo_id: string | null;
  raw_stats: Record<string, number>;

  dk_points: number | null;
  dk_points_breakdown: Record<string, number>;

  match_status: "matched" | "unmatched" | "ambiguous";
  match_confidence: string | null;
  mlb_player_id: string | null;
  candidate_mlb_ids: string[];
  candidate_names: string[];
}

export interface FantasyProsSnapshot {
  slate_date: string;
  retrieved_at: string;
  hitter_count: number;
  pitcher_count: number;
  hitters_matched: number;
  pitchers_matched: number;
  public_api_limited: boolean;
  api_tier: string | null;
  players: FantasyProsPlayerProjection[];
}

/** Reads the latest immutable FantasyPros snapshot for `date`, if any.
 * Pure filesystem read -- never calls the FantasyPros API (see
 * scripts/fetch_fantasypros_projections.py for that). */
export function loadLatestFantasyProsSnapshot(date: string): FantasyProsSnapshot | null {
  const dir = artifactPath(ARTIFACT_DIRS.fantasyProsSnapshots, date);
  const path = findLatestFile(dir, "fantasypros_projection_");
  return safeReadJson<FantasyProsSnapshot>(path);
}

/** { mlb_player_id -> FantasyProsPlayerProjection } map from the latest
 * snapshot for `date` -- only MATCHED players are included (an
 * unmatched/ambiguous FantasyPros row has no mlb_player_id to join by).
 * Returns an empty map (never null/throws) when no snapshot exists yet,
 * so callers can join against it unconditionally, same contract as
 * lib/nativeProjections.ts::getNativeProjectionByPlayerId. */
export function getFantasyProsProjectionByPlayerId(date: string): Map<string, FantasyProsPlayerProjection> {
  const snapshot = loadLatestFantasyProsSnapshot(date);
  const map = new Map<string, FantasyProsPlayerProjection>();
  if (!snapshot) return map;
  for (const p of snapshot.players) {
    if (p.match_status === "matched" && p.mlb_player_id) {
      map.set(p.mlb_player_id, p);
    }
  }
  return map;
}
