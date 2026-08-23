import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;
const DATE = "2026-08-22";
const SLATE_ID = "dkunofficial-152547";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function baseDoc(overrides: Record<string, unknown> = {}) {
  return {
    slate_date: DATE, slate_id: SLATE_ID, generated_at: "2026-08-22T23:59:00+00:00",
    games_total: 3, games_final: 0, all_final: false, games: [],
    players_graded: 0, ml_pitchers_graded: 0, ml_hitters_graded: 0, lineups_graded: 0,
    player_grading: { pitchers: [], hitters: [], combined: [] },
    lineup_grading: { projection_source: "big_money_ml", lineup_sets_found: 0, lineups_total: 0, lineups_fully_graded: 0, lineups: [], highest_actual: null, lowest_actual: null, average_actual: null, average_projected: null, average_projection_error: null },
    lineup_source_comparison: {},
    source_comparison: { pitchers: {}, hitters: {}, combined: {} },
    ceiling_monitor: {}, zero_game_monitor: {}, disaster_pitcher_monitor: {},
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-mlforwardresults-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestMlForwardResults", () => {
  it("returns null when no document exists", async () => {
    const { loadLatestMlForwardResults } = await import("../mlForwardResults");
    expect(loadLatestMlForwardResults(DATE, SLATE_ID)).toBeNull();
  });

  it("returns the latest document by filename timestamp", async () => {
    writeJson(`ml_forward_results/${DATE}/${SLATE_ID}/ml_forward_results_20260822T230000.json`, baseDoc({ players_graded: 1 }));
    writeJson(`ml_forward_results/${DATE}/${SLATE_ID}/ml_forward_results_20260822T235900.json`, baseDoc({ players_graded: 60 }));
    const { loadLatestMlForwardResults } = await import("../mlForwardResults");
    const doc = loadLatestMlForwardResults(DATE, SLATE_ID);
    expect(doc?.players_graded).toBe(60);
  });

  it("never mixes a different slate_id's documents in the same date folder", async () => {
    writeJson(`ml_forward_results/${DATE}/dkunofficial-OTHER/ml_forward_results_20260822T230000.json`, baseDoc({ slate_id: "dkunofficial-OTHER", players_graded: 999 }));
    const { loadLatestMlForwardResults } = await import("../mlForwardResults");
    expect(loadLatestMlForwardResults(DATE, SLATE_ID)).toBeNull();
  });
});

describe("listMlForwardResultsSlateIds / listMlForwardResultsDates", () => {
  it("lists slate ids for a date and dates with any collected slate", async () => {
    writeJson(`ml_forward_results/${DATE}/${SLATE_ID}/ml_forward_results_20260822T230000.json`, baseDoc());
    writeJson(`ml_forward_results/2026-08-21/dkunofficial-A/ml_forward_results_20260821T230000.json`, baseDoc({ slate_date: "2026-08-21", slate_id: "dkunofficial-A" }));
    const { listMlForwardResultsSlateIds, listMlForwardResultsDates } = await import("../mlForwardResults");
    expect(listMlForwardResultsSlateIds(DATE)).toEqual([SLATE_ID]);
    expect(listMlForwardResultsDates()).toEqual([DATE, "2026-08-21"]);
  });
});

describe("pivotModelDisagreements", () => {
  it("pivots per-source records into one row per player with ML/Native/AI side by side", async () => {
    const { pivotModelDisagreements } = await import("../mlForwardResults");
    const records = [
      { player_id: "1", name: "A", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "hitter" as const, projection_source: "big_money_ml", pregame_projection: 10.0, actual_dk: 14.0, error: 4.0, absolute_error: 4.0 },
      { player_id: "1", name: "A", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "hitter" as const, projection_source: "native", pregame_projection: 8.0, actual_dk: 14.0, error: 6.0, absolute_error: 6.0 },
      { player_id: "1", name: "A", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "hitter" as const, projection_source: "ai", pregame_projection: 9.0, actual_dk: 14.0, error: 5.0, absolute_error: 5.0 },
    ];
    const rows = pivotModelDisagreements(records);
    expect(rows).toHaveLength(1);
    expect(rows[0].ml).toBe(10.0);
    expect(rows[0].native).toBe(8.0);
    expect(rows[0].ai).toBe(9.0);
    expect(rows[0].ml_vs_native).toBe(2.0);
    expect(rows[0].ml_vs_ai).toBe(1.0);
  });

  it("excludes a player with no ML projection at all", async () => {
    const { pivotModelDisagreements } = await import("../mlForwardResults");
    const records = [
      { player_id: "2", name: "B", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "hitter" as const, projection_source: "native", pregame_projection: 8.0, actual_dk: 10.0, error: 2.0, absolute_error: 2.0 },
    ];
    expect(pivotModelDisagreements(records)).toEqual([]);
  });

  it("excludes an ML-only player with nothing to disagree with (no Native or AI record at all)", async () => {
    const { pivotModelDisagreements } = await import("../mlForwardResults");
    const records = [
      { player_id: "3", name: "C", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "pitcher" as const, projection_source: "big_money_ml", pregame_projection: 20.0, actual_dk: 22.0, error: 2.0, absolute_error: 2.0 },
    ];
    expect(pivotModelDisagreements(records)).toEqual([]);
  });

  it("never fabricates the missing side when only ONE of Native/AI is present", async () => {
    const { pivotModelDisagreements } = await import("../mlForwardResults");
    const records = [
      { player_id: "4", name: "D", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "pitcher" as const, projection_source: "big_money_ml", pregame_projection: 20.0, actual_dk: 22.0, error: 2.0, absolute_error: 2.0 },
      { player_id: "4", name: "D", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "pitcher" as const, projection_source: "native", pregame_projection: 18.0, actual_dk: 22.0, error: 4.0, absolute_error: 4.0 },
    ];
    const rows = pivotModelDisagreements(records);
    expect(rows).toHaveLength(1);
    expect(rows[0].native).toBe(18.0);
    expect(rows[0].ai).toBeNull();
    expect(rows[0].ml_vs_ai).toBeNull();
  });
});
