import { artifactPath, ARTIFACT_DIRS } from "./artifactRoot";
import { safeReadJson } from "./discovery";

// Milestone 27 -- Part 4 (Results Foundation). Reads the ALREADY-EXISTING
// postgame actual-DK-points pipeline (evaluation/dk_actual_scoring.py +
// scripts/collect_pitcher_results.py / collect_hitter_results.py, both
// pre-existing and committed) -- this module never recomputes actual DK
// points itself, it only reads results/<date>/{pitcher,hitter}_results.json.
// Date-scoped only (never slate-scoped): a player's real fantasy-point
// output is a fact about the game, shared across every slate (Main,
// Turbo, ...) that game happens to be on -- see this project's own
// evaluation/results_collector.py module docstring. Returns "ACTUAL DK"
// as null (never fabricated/zero) for any player with no scoreable
// result yet (game not final, scratched, postponed, etc.).

interface RawResultRecord {
  player_id?: string;
  dfs_points?: number | null;
  status?: string;
}

interface RawResultsDocument {
  results?: RawResultRecord[];
}

async function loadResultsFile(date: string, filename: string): Promise<RawResultRecord[]> {
  const doc = await safeReadJson<RawResultsDocument>(artifactPath(ARTIFACT_DIRS.results, date, filename));
  return doc?.results ?? [];
}

/** { mlb_player_id -> actual DK points }, merged across pitchers and
 * hitters. A player absent from this map has no actual result yet --
 * callers must render that as "NOT LOADED"/blank, never 0. */
export async function loadActualDkPointsByPlayerId(date: string): Promise<Map<string, number>> {
  const map = new Map<string, number>();
  for (const filename of ["pitcher_results.json", "hitter_results.json"]) {
    for (const record of await loadResultsFile(date, filename)) {
      if (record.player_id && typeof record.dfs_points === "number") {
        map.set(record.player_id, record.dfs_points);
      }
    }
  }
  return map;
}

export interface ActualResultsAvailability {
  pitcherResultsExist: boolean;
  hitterResultsExist: boolean;
}

export async function getActualResultsAvailability(date: string): Promise<ActualResultsAvailability> {
  const [pitcherResults, hitterResults] = await Promise.all([
    loadResultsFile(date, "pitcher_results.json"),
    loadResultsFile(date, "hitter_results.json"),
  ]);
  return {
    pitcherResultsExist: pitcherResults.length > 0,
    hitterResultsExist: hitterResults.length > 0,
  };
}
