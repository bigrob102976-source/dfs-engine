import path from "node:path";

import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findAllFiles, findLatestFile, listSlateDates, safeReadJson } from "./discovery";
import type {
  BatterSnapshot,
  DKPlayerPool,
  LineupSet,
  OwnershipEvaluation,
  OwnershipSnapshot,
  PitcherEvaluation,
  PitcherSnapshot,
  SlateIndex,
} from "./types";

export interface Loaded<T> {
  data: T | null;
  path: string | null;
}

function loadLatest<T>(dir: string, prefix: string, ext = ".json"): Loaded<T> {
  const filePath = findLatestFile(dir, prefix, ext);
  return { data: safeReadJson<T>(filePath), path: filePath };
}

export function loadResearchSlate(date: string): Loaded<SlateIndex> {
  const filePath = artifactPath(ARTIFACT_DIRS.research, date, "slate.json");
  const data = safeReadJson<SlateIndex>(filePath);
  return { data, path: data ? filePath : null };
}

export function loadLatestPitcherSnapshot(date: string): Loaded<PitcherSnapshot> {
  return loadLatest<PitcherSnapshot>(artifactPath(ARTIFACT_DIRS.predictions, date), "pitcher_board_");
}

export function loadLatestBatterSnapshot(date: string): Loaded<BatterSnapshot> {
  return loadLatest<BatterSnapshot>(artifactPath(ARTIFACT_DIRS.predictions, date), "batter_board_");
}

export function loadLatestOwnershipSnapshot(date: string): Loaded<OwnershipSnapshot> {
  return loadLatest<OwnershipSnapshot>(artifactPath(ARTIFACT_DIRS.ownershipPredictions, date), "ownership_");
}

export function loadLatestDKPlayerPool(date: string): Loaded<DKPlayerPool> {
  return loadLatest<DKPlayerPool>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_player_pool_");
}

export function loadLatestDkMatchReport(date: string): Loaded<Record<string, unknown>> {
  return loadLatest<Record<string, unknown>>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_match_report_");
}

export function loadLatestLineupSet(date: string): Loaded<LineupSet> {
  return loadLatest<LineupSet>(artifactPath(ARTIFACT_DIRS.lineups, date), "dk_lineups_");
}

/** Every optimizer run saved for a date, oldest first -- lets the
 * Optimizer page offer a run picker when more than one exists (e.g.
 * different objective modes run back to back). */
export function listLineupSets(date: string): Array<Loaded<LineupSet> & { filename: string }> {
  const files = findAllFiles(artifactPath(ARTIFACT_DIRS.lineups, date), "dk_lineups_", ".json");
  return files.map((filePath) => ({
    data: safeReadJson<LineupSet>(filePath),
    path: filePath,
    filename: path.basename(filePath),
  }));
}

export function loadLatestPitcherEvaluation(date: string): Loaded<PitcherEvaluation> {
  return loadLatest<PitcherEvaluation>(artifactPath(ARTIFACT_DIRS.pitcherEvaluations, date), "pitcher_evaluation_");
}

export function listPitcherEvaluations(date: string): Array<Loaded<PitcherEvaluation> & { filename: string }> {
  const files = findAllFiles(artifactPath(ARTIFACT_DIRS.pitcherEvaluations, date), "pitcher_evaluation_", ".json");
  return files.map((filePath) => ({
    data: safeReadJson<PitcherEvaluation>(filePath),
    path: filePath,
    filename: path.basename(filePath),
  }));
}

/** Every ownership evaluation for a date across ALL contests (never
 * merged -- see evaluation/ownership_evaluation_persistence.py). */
export function listOwnershipEvaluations(date: string): Array<Loaded<OwnershipEvaluation> & { filename: string }> {
  const files = findAllFiles(artifactPath(ARTIFACT_DIRS.ownershipEvaluations, date), "contest_", ".json");
  return files.map((filePath) => ({
    data: safeReadJson<OwnershipEvaluation>(filePath),
    path: filePath,
    filename: path.basename(filePath),
  }));
}

export function loadLatestOwnershipEvaluation(date: string): Loaded<OwnershipEvaluation> {
  const all = listOwnershipEvaluations(date);
  if (all.length === 0) return { data: null, path: null };
  const last = all[all.length - 1];
  return { data: last.data, path: last.path };
}

/** Union of every slate date that has ANY artifact, newest first --
 * used by the History page to know which dates to chart. */
export function listAllKnownSlateDates(): string[] {
  const dirs = [
    ARTIFACT_DIRS.research,
    ARTIFACT_DIRS.predictions,
    ARTIFACT_DIRS.ownershipPredictions,
    ARTIFACT_DIRS.dfsInput,
    ARTIFACT_DIRS.lineups,
    ARTIFACT_DIRS.pitcherEvaluations,
    ARTIFACT_DIRS.ownershipEvaluations,
  ];
  const dates = new Set<string>();
  for (const dir of dirs) {
    for (const date of listSlateDates(artifactPath(dir))) dates.add(date);
  }
  return Array.from(dates).sort().reverse();
}

export function latestKnownSlateDate(): string | null {
  const dates = listAllKnownSlateDates();
  return dates.length ? dates[0] : null;
}
