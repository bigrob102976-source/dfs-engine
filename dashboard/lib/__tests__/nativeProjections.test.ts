import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;
const DATE = "2026-08-17";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function nativePlayerRecord(overrides: Record<string, unknown> = {}) {
  return {
    player_id: "592450",
    name: "Bryce Harper",
    team: "PHI",
    player_type: "hitter",
    opponent: "ATL",
    game_id: "824882",
    salary: 5500,
    positions: ["1B"],
    batting_order: 3,
    native_projection: 9.61,
    native_ceiling: 15.28,
    native_floor: 3.94,
    confidence: 78.5,
    variance: 8.2,
    model_version: "1.0.0",
    hitter_opportunity: { expected_pa: 4.4, pa_confidence: 90.0, reasons: ["Batting order 3 (confirmed lineup) -> 4.4 expected PA"] },
    pitcher_opportunity: null,
    hitter_components: {
      singles: { expected_count: 0.6, dk_points_per_event: 3.0, dk_points: 1.8, reason: null },
      doubles: { expected_count: 0.2, dk_points_per_event: 5.0, dk_points: 1.0, reason: null },
      triples: { expected_count: 0.02, dk_points_per_event: 8.0, dk_points: 0.16, reason: null },
      home_runs: { expected_count: 0.16, dk_points_per_event: 10.0, dk_points: 1.6, reason: null },
      walks: { expected_count: 0.4, dk_points_per_event: 2.0, dk_points: 0.8, reason: null },
      hit_by_pitch: { expected_count: 0.04, dk_points_per_event: 2.0, dk_points: 0.08, reason: null },
      stolen_bases: { expected_count: 0.05, dk_points_per_event: 5.0, dk_points: 0.25, reason: null },
      runs: { expected_count: 0.45, dk_points_per_event: 2.0, dk_points: 0.9, reason: "Linear approximation" },
      rbi: { expected_count: 0.18, dk_points_per_event: 2.0, dk_points: 0.36, reason: "Linear approximation" },
      strikeouts_expected: 0.9,
    },
    pitcher_components: null,
    input_coverage: { fields_available: 9, fields_total: 12, missing_fields: ["season.hit_by_pitch"], fraction: 0.75 },
    reasons: ["Batting order 3 (confirmed lineup) -> 4.4 expected PA"],
    warnings: [],
    generated_at: "2026-08-17T19:00:00Z",
    source_pitcher_snapshot_path: null,
    source_batter_snapshot_path: "predictions/2026-08-17/batter_board_20260817T190118.json",
    source_environment_snapshot_path: null,
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-nativeprojections-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestNativeProjectionSnapshot", () => {
  it("returns null when no snapshot exists", async () => {
    const { loadLatestNativeProjectionSnapshot } = await import("../nativeProjections");
    expect(loadLatestNativeProjectionSnapshot(DATE)).toBeNull();
  });

  it("returns the latest snapshot by filename timestamp", async () => {
    writeJson(`native_projection_snapshots/${DATE}/native_projection_20260817T180000.json`, {
      slate_date: DATE, generated_at: "2026-08-17T18:00:00Z", model_version: "1.0.0",
      pitcher_snapshot_path: null, batter_snapshot_path: null, environment_snapshot_path: null,
      player_count: 0, players: [], warnings: [],
    });
    writeJson(`native_projection_snapshots/${DATE}/native_projection_20260817T190000.json`, {
      slate_date: DATE, generated_at: "2026-08-17T19:00:00Z", model_version: "1.0.0",
      pitcher_snapshot_path: null, batter_snapshot_path: null, environment_snapshot_path: null,
      player_count: 0, players: [], warnings: [],
    });
    const { loadLatestNativeProjectionSnapshot } = await import("../nativeProjections");
    const latest = loadLatestNativeProjectionSnapshot(DATE);
    expect(latest?.generated_at).toBe("2026-08-17T19:00:00Z");
  });
});

describe("getNativeProjectionByPlayerId", () => {
  it("returns an empty map (never throws) when no snapshot exists", async () => {
    const { getNativeProjectionByPlayerId } = await import("../nativeProjections");
    const map = getNativeProjectionByPlayerId(DATE);
    expect(map.size).toBe(0);
  });

  it("builds a map keyed by player_id with every native field intact", async () => {
    writeJson(`native_projection_snapshots/${DATE}/native_projection_20260817T180000.json`, {
      slate_date: DATE, generated_at: "2026-08-17T18:00:00Z", model_version: "1.0.0",
      pitcher_snapshot_path: null, batter_snapshot_path: null, environment_snapshot_path: null,
      player_count: 1, players: [nativePlayerRecord()], warnings: [],
    });
    const { getNativeProjectionByPlayerId } = await import("../nativeProjections");
    const map = getNativeProjectionByPlayerId(DATE);
    const player = map.get("592450");
    expect(player).toBeDefined();
    expect(player?.native_projection).toBe(9.61);
    expect(player?.native_ceiling).toBe(15.28);
    expect(player?.confidence).toBe(78.5);
    expect(player?.hitter_components?.home_runs.dk_points).toBe(1.6);
    expect(player?.pitcher_components).toBeNull();
    expect(player?.input_coverage?.fraction).toBe(0.75);
  });
});
