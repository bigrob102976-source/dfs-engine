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

function pitcherRecord(overrides: Record<string, unknown> = {}) {
  return {
    player_id: "543037", dk_player_id: "dk543037", name: "Gerrit Cole", team: "NYY", opponent: "BOS",
    game_id: "g1", salary: 10500, projection: 18.4, model_version: "1.0.0", data_quality_score: 0.97,
    feature_coverage: 0.97, missing_features: [], projection_status: "LIVE_PREGAME",
    feature_timestamp: "2026-08-22T17:00:00+00:00", game_scheduled_start_utc: "2026-08-22T23:00:00Z", warnings: [],
    ...overrides,
  };
}

function hitterRecord(overrides: Record<string, unknown> = {}) {
  return {
    player_id: "660271", dk_player_id: "dk660271", name: "Shohei Ohtani", team: "LAD", opponent: "PIT",
    game_id: "g2", salary: 6700, batting_order: 1, projection: 10.77, model_version: "1.0.0",
    data_quality_score: 0.988, feature_coverage: 0.99, missing_features: [], projection_status: "LIVE_PREGAME",
    feature_timestamp: "2026-08-22T17:00:00+00:00", game_scheduled_start_utc: "2026-08-22T23:10:00Z", warnings: [],
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-mlprojections-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestMlProjectionSnapshot / loadLatestMlHitterProjectionSnapshot", () => {
  it("each reads only its own filename-prefixed stream, never the other's", async () => {
    writeJson(`ml_projection_snapshots/${DATE}/ml_projection_20260822T170000.json`, {
      slate_date: DATE, generated_at: "2026-08-22T17:00:00+00:00", model_version: "1.0.0", warehouse_version: "v1",
      raw_dk_pitcher_count: 1, starting_pitcher_count: 1, ml_eligible_pitcher_count: 1,
      ml_projections_generated: 1, ml_projections_missing: 0, feature_parity_summary: {}, players: [pitcherRecord()], warnings: [],
    });
    writeJson(`ml_projection_snapshots/${DATE}/ml_hitter_projection_20260822T170000.json`, {
      slate_date: DATE, generated_at: "2026-08-22T17:00:00+00:00", model_version: "1.0.0", warehouse_version: "v1",
      raw_dk_hitter_count: 1, confirmed_starting_hitter_count: 1, ml_eligible_hitter_count: 1,
      ml_projections_generated: 1, ml_projections_missing: 0, feature_parity_summary: {}, players: [hitterRecord()], warnings: [],
    });

    const { loadLatestMlProjectionSnapshot, loadLatestMlHitterProjectionSnapshot } = await import("../mlProjections");
    const pitcherDoc = await loadLatestMlProjectionSnapshot(DATE);
    const hitterDoc = await loadLatestMlHitterProjectionSnapshot(DATE);

    expect(pitcherDoc?.players).toHaveLength(1);
    expect(pitcherDoc?.players[0].player_id).toBe("543037");
    expect(hitterDoc?.players).toHaveLength(1);
    expect(hitterDoc?.players[0].player_id).toBe("660271");
  });

  it("returns null when no snapshot exists for either stream", async () => {
    const { loadLatestMlProjectionSnapshot, loadLatestMlHitterProjectionSnapshot } = await import("../mlProjections");
    expect(await loadLatestMlProjectionSnapshot(DATE)).toBeNull();
    expect(await loadLatestMlHitterProjectionSnapshot(DATE)).toBeNull();
  });
});

describe("getMlProjectionByPlayerId (unified BIG MONEY ML map)", () => {
  it("returns an empty map (never throws) when no snapshots exist", async () => {
    const { getMlProjectionByPlayerId } = await import("../mlProjections");
    const map = await getMlProjectionByPlayerId(DATE);
    expect(map.size).toBe(0);
  });

  it("merges pitcher and hitter snapshots into one map keyed by player_id", async () => {
    writeJson(`ml_projection_snapshots/${DATE}/ml_projection_20260822T170000.json`, {
      slate_date: DATE, generated_at: "2026-08-22T17:00:00+00:00", model_version: "1.0.0", warehouse_version: "v1",
      raw_dk_pitcher_count: 1, starting_pitcher_count: 1, ml_eligible_pitcher_count: 1,
      ml_projections_generated: 1, ml_projections_missing: 0, feature_parity_summary: {}, players: [pitcherRecord()], warnings: [],
    });
    writeJson(`ml_projection_snapshots/${DATE}/ml_hitter_projection_20260822T170000.json`, {
      slate_date: DATE, generated_at: "2026-08-22T17:00:00+00:00", model_version: "1.0.0", warehouse_version: "v1",
      raw_dk_hitter_count: 1, confirmed_starting_hitter_count: 1, ml_eligible_hitter_count: 1,
      ml_projections_generated: 1, ml_projections_missing: 0, feature_parity_summary: {}, players: [hitterRecord()], warnings: [],
    });

    const { getMlProjectionByPlayerId } = await import("../mlProjections");
    const map = await getMlProjectionByPlayerId(DATE);
    expect(map.size).toBe(2);

    const pitcher = map.get("543037");
    expect(pitcher?.projection).toBe(18.4);
    expect(pitcher?.player_type).toBe("pitcher");
    expect(pitcher?.batting_order).toBeNull();

    const hitter = map.get("660271");
    expect(hitter?.projection).toBe(10.77);
    expect(hitter?.player_type).toBe("hitter");
    expect(hitter?.batting_order).toBe(1);
  });

  it("works when only the hitter stream has data (pitcher snapshot missing)", async () => {
    writeJson(`ml_projection_snapshots/${DATE}/ml_hitter_projection_20260822T170000.json`, {
      slate_date: DATE, generated_at: "2026-08-22T17:00:00+00:00", model_version: "1.0.0", warehouse_version: "v1",
      raw_dk_hitter_count: 1, confirmed_starting_hitter_count: 1, ml_eligible_hitter_count: 1,
      ml_projections_generated: 1, ml_projections_missing: 0, feature_parity_summary: {}, players: [hitterRecord()], warnings: [],
    });
    const { getMlProjectionByPlayerId } = await import("../mlProjections");
    const map = await getMlProjectionByPlayerId(DATE);
    expect(map.size).toBe(1);
    expect(map.get("660271")?.player_type).toBe("hitter");
  });
});

describe("getMlHitterProjectionByPlayerId", () => {
  it("builds a map keyed by player_id with batting_order intact", async () => {
    writeJson(`ml_projection_snapshots/${DATE}/ml_hitter_projection_20260822T170000.json`, {
      slate_date: DATE, generated_at: "2026-08-22T17:00:00+00:00", model_version: "1.0.0", warehouse_version: "v1",
      raw_dk_hitter_count: 1, confirmed_starting_hitter_count: 1, ml_eligible_hitter_count: 1,
      ml_projections_generated: 1, ml_projections_missing: 0, feature_parity_summary: {}, players: [hitterRecord()], warnings: [],
    });
    const { getMlHitterProjectionByPlayerId } = await import("../mlProjections");
    const map = await getMlHitterProjectionByPlayerId(DATE);
    const player = map.get("660271");
    expect(player?.batting_order).toBe(1);
    expect(player?.data_quality_score).toBe(0.988);
  });
});
