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

async function loadLatest<T>(dir: string, prefix: string, ext = ".json"): Promise<Loaded<T>> {
  const filePath = await findLatestFile(dir, prefix, ext);
  return { data: await safeReadJson<T>(filePath), path: filePath };
}

export async function loadResearchSlate(date: string): Promise<Loaded<SlateIndex>> {
  const filePath = artifactPath(ARTIFACT_DIRS.research, date, "slate.json");
  const data = await safeReadJson<SlateIndex>(filePath);
  return { data, path: data ? filePath : null };
}

export async function loadLatestPitcherSnapshot(date: string): Promise<Loaded<PitcherSnapshot>> {
  return loadLatest<PitcherSnapshot>(artifactPath(ARTIFACT_DIRS.predictions, date), "pitcher_board_");
}

export async function loadLatestBatterSnapshot(date: string): Promise<Loaded<BatterSnapshot>> {
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
export async function loadLatestOwnershipSnapshot(date: string, slateId?: string | null): Promise<Loaded<OwnershipSnapshot>> {
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
export async function loadLatestDKPlayerPool(date: string, slateId?: string | null): Promise<Loaded<DKPlayerPool>> {
  if (!slateId) {
    return loadLatest<DKPlayerPool>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_player_pool_");
  }
  const dir = artifactPath(ARTIFACT_DIRS.dfsInput, date);
  const files = await findAllFiles(dir, "dk_player_pool_");
  for (let i = files.length - 1; i >= 0; i -= 1) {
    const data = await safeReadJson<DKPlayerPool>(files[i]);
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
export async function loadLatestDkMatchReport(date: string, slateId?: string | null): Promise<Loaded<Record<string, unknown>>> {
  if (!slateId) {
    return loadLatest<Record<string, unknown>>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "dk_match_report_");
  }
  const pool = await loadLatestDKPlayerPool(date, slateId);
  if (!pool.path) return { data: null, path: null };
  const reportPath = matchReportPathForPool(pool.path);
  return { data: await safeReadJson<Record<string, unknown>>(reportPath), path: reportPath };
}

/** The most recent scripts/fetch_dfs_slate.py output for `date` -- the
 * DFS salary provider's own status/name/mock-flag/selected-slate record.
 * Read-only, same immutable-snapshot convention as every other loader
 * here; the dashboard never re-derives this, it only displays what the
 * pipeline already wrote (see runner.ts's dfsSalaries step). */
export async function loadLatestProviderSlate(date: string): Promise<Loaded<Record<string, unknown>>> {
  return loadLatest<Record<string, unknown>>(artifactPath(ARTIFACT_DIRS.dfsInput, date), "provider_slate_");
}

/** M32.7: real, live MLB game status (Scheduled/Live/Final/Postponed --
 * research/normalizer.py's own status field, sourced from MLB Stats
 * API's schedule response) for every game on `date` -- schedule-derived,
 * not a timestamped snapshot (see research_output/'s own convention,
 * same as loadResearchSlate above). Used ONLY to classify slate
 * completion stage (lib/slateReadiness.ts) honestly from real data --
 * never fabricated. */
export async function loadResearchGames(date: string): Promise<Loaded<ResearchGame[]>> {
  const filePath = artifactPath(ARTIFACT_DIRS.research, date, "games.json");
  const data = await safeReadJson<ResearchGame[]>(filePath);
  return { data, path: data ? filePath : null };
}

export async function loadLatestLineupSet(date: string): Promise<Loaded<LineupSet>> {
  return loadLatest<LineupSet>(artifactPath(ARTIFACT_DIRS.lineups, date), "dk_lineups_");
}

/** Every optimizer run saved for a date, oldest first -- lets the
 * Optimizer page offer a run picker when more than one exists (e.g.
 * different objective modes run back to back). */
export async function listLineupSets(date: string): Promise<Array<Loaded<LineupSet> & { filename: string }>> {
  const files = await findAllFiles(artifactPath(ARTIFACT_DIRS.lineups, date), "dk_lineups_", ".json");
  return Promise.all(
    files.map(async (filePath) => ({
      data: await safeReadJson<LineupSet>(filePath),
      path: filePath,
      filename: path.basename(filePath),
    })),
  );
}

export async function loadLatestPitcherEvaluation(date: string): Promise<Loaded<PitcherEvaluation>> {
  return loadLatest<PitcherEvaluation>(artifactPath(ARTIFACT_DIRS.pitcherEvaluations, date), "pitcher_evaluation_");
}

export async function listPitcherEvaluations(date: string): Promise<Array<Loaded<PitcherEvaluation> & { filename: string }>> {
  const files = await findAllFiles(artifactPath(ARTIFACT_DIRS.pitcherEvaluations, date), "pitcher_evaluation_", ".json");
  return Promise.all(
    files.map(async (filePath) => ({
      data: await safeReadJson<PitcherEvaluation>(filePath),
      path: filePath,
      filename: path.basename(filePath),
    })),
  );
}

/** Every ownership evaluation for a date across ALL contests (never
 * merged -- see evaluation/ownership_evaluation_persistence.py). */
export async function listOwnershipEvaluations(date: string): Promise<Array<Loaded<OwnershipEvaluation> & { filename: string }>> {
  const files = await findAllFiles(artifactPath(ARTIFACT_DIRS.ownershipEvaluations, date), "contest_", ".json");
  return Promise.all(
    files.map(async (filePath) => ({
      data: await safeReadJson<OwnershipEvaluation>(filePath),
      path: filePath,
      filename: path.basename(filePath),
    })),
  );
}

export async function loadLatestOwnershipEvaluation(date: string): Promise<Loaded<OwnershipEvaluation>> {
  const all = await listOwnershipEvaluations(date);
  if (all.length === 0) return { data: null, path: null };
  const last = all[all.length - 1];
  return { data: last.data, path: last.path };
}

/** Union of every slate date that has ANY artifact, newest first --
 * used by the History page to know which dates to chart. */
export async function listAllKnownSlateDates(): Promise<string[]> {
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
    for (const date of await listSlateDates(artifactPath(dir))) dates.add(date);
  }
  return Array.from(dates).sort().reverse();
}

export async function latestKnownSlateDate(): Promise<string | null> {
  const dates = await listAllKnownSlateDates();
  return dates.length ? dates[0] : null;
}
