import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetStorageForTests } from "../storage/getStorage";

let tmpDir: string;
const DATE = "2026-08-22";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function pitcherDoc(overrides: Record<string, unknown> = {}) {
  return {
    slate_date: DATE, generated_at: "2026-08-22T20:18:43+00:00", model_version: "1.0.0", warehouse_version: "v1",
    raw_dk_pitcher_count: 30, starting_pitcher_count: 22, ml_eligible_pitcher_count: 22,
    ml_projections_generated: 22, ml_projections_missing: 0, feature_parity_summary: {}, players: [], warnings: [],
    ...overrides,
  };
}

function hitterDoc(overrides: Record<string, unknown> = {}) {
  return {
    slate_date: DATE, generated_at: "2026-08-22T22:11:56+00:00", model_version: "1.0.0", warehouse_version: "v1",
    raw_dk_hitter_count: 461, confirmed_starting_hitter_count: 81, ml_eligible_hitter_count: 81,
    ml_projections_generated: 81, ml_projections_missing: 0, feature_parity_summary: {}, players: [], warnings: [],
    ...overrides,
  };
}

function poolPlayer(overrides: Record<string, unknown> = {}) {
  return {
    dk_player_id: "d1", name: "Player", team: "NYY", player_type: "hitter", dk_positions: ["OF"], salary: 4000,
    mlb_player_id: "1", opponent: "BOS", game_id: "g1", batting_order: 1, projection: 8, ceiling: 15, floor: 3,
    overall_score: null, risk_score: null, confidence: null, tags: [], reasons: [], season_sample_size: null,
    lineup_status: "active", match_status: "matched", eligibility_status: "STARTING_HITTER", optimizer_eligible: true,
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-bigmoneymloptimizer-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("getBigMoneyMlCoverage", () => {
  it("returns all zeros when no ML snapshots exist yet", async () => {
    const { getBigMoneyMlCoverage } = await import("../bigMoneyMlOptimizer");
    const coverage = await getBigMoneyMlCoverage(DATE);
    expect(coverage.pitchers).toEqual({ generated: 0, eligible: 0 });
    expect(coverage.hitters).toEqual({ generated: 0, eligible: 0 });
    expect(coverage.combined).toEqual({ generated: 0, eligible: 0 });
    expect(coverage.pitcherModelVersion).toBeNull();
  });

  it("reports pitcher/hitter/combined coverage straight from the persisted snapshots", async () => {
    writeJson(`ml_projection_snapshots/${DATE}/ml_projection_20260822T201843.json`, pitcherDoc());
    writeJson(`ml_projection_snapshots/${DATE}/ml_hitter_projection_20260822T221156.json`, hitterDoc());

    const { getBigMoneyMlCoverage } = await import("../bigMoneyMlOptimizer");
    const coverage = await getBigMoneyMlCoverage(DATE);
    expect(coverage.pitchers).toEqual({ generated: 22, eligible: 22 });
    expect(coverage.hitters).toEqual({ generated: 81, eligible: 81 });
    expect(coverage.combined).toEqual({ generated: 103, eligible: 103 });
    expect(coverage.pitcherModelVersion).toBe("1.0.0");
    expect(coverage.hitterModelVersion).toBe("1.0.0");
    expect(coverage.pitcherSnapshotGeneratedAt).toBe("2026-08-22T20:18:43+00:00");
    expect(coverage.hitterSnapshotGeneratedAt).toBe("2026-08-22T22:11:56+00:00");
  });

  it("reports honest partial coverage when ML projections are missing for some players", async () => {
    writeJson(`ml_projection_snapshots/${DATE}/ml_projection_20260822T201843.json`, pitcherDoc({ ml_projections_generated: 20, ml_projections_missing: 2 }));
    const { getBigMoneyMlCoverage } = await import("../bigMoneyMlOptimizer");
    const coverage = await getBigMoneyMlCoverage(DATE);
    expect(coverage.pitchers).toEqual({ generated: 20, eligible: 22 });
  });

  it("counts a game as waiting for lineups only when NO hitter for that game is confirmed", async () => {
    writeJson(`dfs_input/${DATE}/dk_player_pool_20260822T202424.json`, {
      slate_date: DATE, generated_at_utc: "x", player_count: 3,
      players: [
        poolPlayer({ game_id: "g1", eligibility_status: "STARTING_HITTER" }),
        poolPlayer({ dk_player_id: "d2", game_id: "g2", eligibility_status: "LINEUP_UNCONFIRMED" }),
        poolPlayer({ dk_player_id: "d3", game_id: "g2", eligibility_status: "LINEUP_UNCONFIRMED" }),
      ],
    });
    const { getBigMoneyMlCoverage } = await import("../bigMoneyMlOptimizer");
    const coverage = await getBigMoneyMlCoverage(DATE);
    expect(coverage.gamesWaitingForLineups).toBe(1); // only g2
  });

  it("never counts a game as waiting once at least one of its hitters is confirmed", async () => {
    writeJson(`dfs_input/${DATE}/dk_player_pool_20260822T202424.json`, {
      slate_date: DATE, generated_at_utc: "x", player_count: 2,
      players: [
        poolPlayer({ dk_player_id: "d1", game_id: "g1", eligibility_status: "STARTING_HITTER" }),
        poolPlayer({ dk_player_id: "d2", game_id: "g1", eligibility_status: "LINEUP_UNCONFIRMED" }),
      ],
    });
    const { getBigMoneyMlCoverage } = await import("../bigMoneyMlOptimizer");
    const coverage = await getBigMoneyMlCoverage(DATE);
    expect(coverage.gamesWaitingForLineups).toBe(0);
  });
});
