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
  ResearchGame,
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

/** Milestone 26: ownership is estimated relative to ONE slate's player
 * pool, so when `slateId` is given this reads ownership_predictions/
 * <date>/<slateId>/ownership_*.json -- a DIFFERENT slate sharing the
 * same date never overwrites/leaks into this result (see
 * ownership/persistence.py's module docstring for the save-side half
 * of this fix). Omitting `slateId` preserves the exact pre-Milestone-26
 * date-only path, so artifacts written before this milestone remain
 * readable unchanged. */
export function loadLatestOwnershipSnapshot(date: string, slateId?: string | null): Loaded<OwnershipSnapshot> {
  const dir = slateId ? artifactPath(ARTIFACT_DIRS.ownershipPredictions, date, slateId) : artifactPath(ARTIFACT_DIRS.ownershipPredictions, date);
  return loadLatest<OwnershipSnapshot>(dir, "ownership_");
}

/** Milestone 26: dfs_input/<date>/dk_player_pool_*.json isn't stored in
 * per-slate subfolders (unlike ownership_predictions/ -- see
 * ownership/persistence.py's module docstring for why that one needed
 * to be) -- but every pool built via the provider pipeline (scripts/
 * build_dfs_pool_from_provider.py) already stamps its own
 * `selected_slate_id` on the saved document. When `slateId` is given,
 * this scans every pool file for the date (oldest first) and returns
 * the LATEST one whose selected_slate_id matches, so a page showing
 * "Turbo" never displays salaries/positions from whichever slate the
 * Optimizer happened to build most recently. Omitting `slateId`
 * preserves the exact previous "just take the newest file" behavior. */
export function loadLatestDKPlayerPool(date: string, slateId?: string | null): Loaded<DKPlayerPool> {
  if (!slateId) {
    return loadLatest<DKPlayerPool>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_player_pool_");
  }
  const dir = artifactPath(ARTIFACT_DIRS.dfsInput, date);
  const files = findAllFiles(dir, "dk_player_pool_");
  for (let i = files.length - 1; i >= 0; i -= 1) {
    const data = safeReadJson<DKPlayerPool>(files[i]);
    if (data && data.selected_slate_id === slateId) {
      return { data, path: files[i] };
    }
  }
  return { data: null, path: null };
}

function matchReportPathForPool(poolPath: string): string {
  return path.join(path.dirname(poolPath), path.basename(poolPath).replace("dk_player_pool_", "dk_match_report_"));
}

/** See loadLatestDKPlayerPool's docstring -- the match report shares
 * its pool's exact timestamp (both written by the same save_pool()
 * call), so resolving the right pool for a slate and swapping the
 * filename prefix finds its match report too, without dk_match_report_
 * files needing their own slate_id field. */
export function loadLatestDkMatchReport(date: string, slateId?: string | null): Loaded<Record<string, unknown>> {
  if (!slateId) {
    return loadLatest<Record<string, unknown>>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_match_report_");
  }
  const pool = loadLatestDKPlayerPool(date, slateId);
  if (!pool.path) return { data: null, path: null };
  const reportPath = matchReportPathForPool(pool.path);
  return { data: safeReadJson<Record<string, unknown>>(reportPath), path: reportPath };
}

/** The most recent scripts/fetch_dfs_slate.py output for `date` -- the
 * DFS salary provider's own status/name/mock-flag/selected-slate record.
 * Read-only, same immutable-snapshot convention as every other loader
 * here; the dashboard never re-derives this, it only displays what the
 * pipeline already wrote (see runner.ts's dfsSalaries step). */
export function loadLatestProviderSlate(date: string): Loaded<Record<string, unknown>> {
  return loadLatest<Record<string, unknown>>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "provider_slate_");
}

/** M32.7: real, live MLB game status (Scheduled/Live/Final/Postponed --
 * research/normalizer.py's own status field, sourced from MLB Stats
 * API's schedule response) for every game on `date` -- schedule-derived,
 * not a timestamped snapshot (see research_output/'s own convention,
 * same as loadResearchSlate above). Used ONLY to classify slate
 * completion stage (lib/slateReadiness.ts) honestly from real data --
 * never fabricated. */
export function loadResearchGames(date: string): Loaded<ResearchGame[]> {
  const filePath = artifactPath(ARTIFACT_DIRS.research, date, "games.json");
  const data = safeReadJson<ResearchGame[]>(filePath);
  return { data, path: data ? filePath : null };
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
