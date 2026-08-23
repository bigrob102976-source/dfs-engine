// BlueCollar DFS integration: pure, read-only loaders for the immutable
// bluecollar_projection_snapshots/<date>/<dk_slate_id>/bluecollar_projection_*.json
// artifact (bluecollar/*.py's output) -- never calls the BlueCollar API,
// never triggers generation (see scripts/fetch_bluecollar_projections.py
// for that, invoked only from the admin Process/Refresh pipeline --
// lib/slatePipeline.ts). Mirrors lib/fantasyProsProjections.ts's loader
// shape, but ALWAYS slate-scoped (BlueCollar's data genuinely differs
// per DK slate -- Main/Turbo/Afternoon each have a different player
// pool), field-for-field with bluecollar/models.py's dataclasses.
//
// IMPORTANT MODEL RULE (per this integration's own spec): BlueCollar is
// a COMPARISON + OPTIONAL ADMIN-ONLY OPTIMIZER SOURCE only. Nothing here
// (or anywhere else in this integration) feeds a BlueCollar value into
// Big Money Native/AI/ML's own computation.
//
// ZERO-VALUE RULE: `usable_projection` is null whenever BlueCollar
// reported no genuinely usable projection (raw value <= 0, or missing)
// -- see bluecollar/build.py's module docstring. UI code must always
// read `usable_projection` (never `raw_projection`) when deciding what
// to show a member, and must render null as "NOT AVAILABLE", never 0.

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findLatestFile, safeReadJson } from "./discovery";

export interface BlueCollarPlayerProjection {
  bluecollar_local_id: string;
  name: string;
  team: string;
  position: string;
  opponent: string | null;
  salary: number | null;

  raw_projection: number | null;
  usable_projection: number | null;

  match_status: "matched" | "unmatched" | "ambiguous";
  match_confidence: string | null;
  mlb_player_id: string | null;
  candidate_mlb_ids: string[];
  candidate_names: string[];
}

export interface BlueCollarSnapshot {
  slate_date: string;
  dk_slate_id: string;
  bluecollar_slate_id: string | null;
  bluecollar_slate_name: string | null;
  bluecollar_updated: string | null;
  retrieved_at: string;
  slate_match_status: string;
  slate_match_reason: string | null;

  player_count: number;
  matched_count: number;
  usable_projection_count: number;

  players: BlueCollarPlayerProjection[];
}

/** Reads the latest immutable BlueCollar snapshot for (date, dk_slate_id),
 * if any. Pure filesystem read -- never calls the BlueCollar API (see
 * scripts/fetch_bluecollar_projections.py for that). `slateId` is
 * required (unlike FantasyPros' date-only loader) since BlueCollar is
 * always fetched scoped to one specific DK slate. */
export function loadLatestBlueCollarSnapshot(date: string, slateId: string | null): BlueCollarSnapshot | null {
  if (!slateId) return null;
  const dir = artifactPath(ARTIFACT_DIRS.blueCollarProjectionSnapshots, date, slateId);
  const path = findLatestFile(dir, "bluecollar_projection_");
  return safeReadJson<BlueCollarSnapshot>(path);
}

/** { mlb_player_id -> BlueCollarPlayerProjection } map from the latest
 * snapshot for (date, slateId) -- only MATCHED players are included (an
 * unmatched/ambiguous BlueCollar row has no mlb_player_id to join by).
 * Returns an empty map (never null/throws) when no snapshot exists yet,
 * so callers can join against it unconditionally, same contract as
 * lib/nativeProjections.ts::getNativeProjectionByPlayerId. */
export function getBlueCollarProjectionByPlayerId(date: string, slateId: string | null): Map<string, BlueCollarPlayerProjection> {
  const snapshot = loadLatestBlueCollarSnapshot(date, slateId);
  const map = new Map<string, BlueCollarPlayerProjection>();
  if (!snapshot) return map;
  for (const p of snapshot.players) {
    if (p.match_status === "matched" && p.mlb_player_id) {
      map.set(p.mlb_player_id, p);
    }
  }
  return map;
}
