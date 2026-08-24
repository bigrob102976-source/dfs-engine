import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetStorageForTests } from "../storage/getStorage";

let tmpDir: string;
const DATE = "2026-08-13";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function adjustedRecord(overrides: Record<string, unknown> = {}) {
  return {
    independent_player_id: "h1",
    name: "Kyle Schwarber",
    team: "PHI",
    player_type: "hitter",
    external_player_id: "mock-ext-h1",
    external_projection: 11.2,
    external_ceiling: 20.0,
    external_floor: 5.0,
    external_provider: "MOCK EXTERNAL PROJECTIONS",
    external_provider_timestamp: "2026-08-13T18:00:00Z",
    independent_projection: 11.9,
    independent_ceiling: 21.0,
    independent_floor: 5.5,
    adjusted_projection: 12.1,
    adjusted_ceiling: 21.6,
    adjusted_floor: 5.4,
    adjustment_delta: 0.9,
    adjustment_percent: 8.0,
    adjustment_confidence: 85.0,
    adjustment_reasons: ["positive recent hard-hit trend"],
    adjustments: [{ factor: "recent_hard_hit_trend", delta: 0.4, reason: "positive recent hard-hit trend", confidence: 85.0 }],
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-externalprojections-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestBaselineSnapshot", () => {
  it("returns null when no snapshot exists", async () => {
    const { loadLatestBaselineSnapshot } = await import("../externalProjections");
    expect(await loadLatestBaselineSnapshot(DATE)).toBeNull();
  });

  it("returns the latest snapshot by filename timestamp", async () => {
    writeJson(`external_projection_snapshots/${DATE}/provider_mock_external_projections_20260813T180000.json`, {
      slate_date: DATE, provider: "mock_external_projections", retrieved_at: "2026-08-13T18:00:00Z", players: [],
    });
    writeJson(`external_projection_snapshots/${DATE}/provider_mock_external_projections_20260813T190000.json`, {
      slate_date: DATE, provider: "mock_external_projections", retrieved_at: "2026-08-13T19:00:00Z", players: [],
    });
    const { loadLatestBaselineSnapshot } = await import("../externalProjections");
    const latest = await loadLatestBaselineSnapshot(DATE);
    expect(latest?.retrieved_at).toBe("2026-08-13T19:00:00Z");
  });
});

describe("loadLatestAdjustedSnapshot", () => {
  it("returns null when no snapshot exists", async () => {
    const { loadLatestAdjustedSnapshot } = await import("../externalProjections");
    expect(await loadLatestAdjustedSnapshot(DATE)).toBeNull();
  });

  it("reads records from the latest adjusted snapshot", async () => {
    writeJson(`adjusted_projection_snapshots/${DATE}/adjusted_20260813T200000.json`, {
      slate_date: DATE, generated_at: "2026-08-13T20:00:00Z", records: [adjustedRecord()],
    });
    const { loadLatestAdjustedSnapshot } = await import("../externalProjections");
    const snapshot = await loadLatestAdjustedSnapshot(DATE);
    expect(snapshot?.records).toHaveLength(1);
    expect(snapshot?.records[0].name).toBe("Kyle Schwarber");
  });
});

describe("getProjectionComparisonByPlayerId", () => {
  it("returns an empty map (never throws) when no adjusted snapshot exists", async () => {
    const { getProjectionComparisonByPlayerId } = await import("../externalProjections");
    const map = await getProjectionComparisonByPlayerId(DATE);
    expect(map.size).toBe(0);
  });

  it("builds a comparison row keyed by independent_player_id, matching the milestone's worked example", async () => {
    writeJson(`adjusted_projection_snapshots/${DATE}/adjusted_20260813T200000.json`, {
      slate_date: DATE, generated_at: "2026-08-13T20:00:00Z", records: [adjustedRecord()],
    });
    const { getProjectionComparisonByPlayerId } = await import("../externalProjections");
    const map = await getProjectionComparisonByPlayerId(DATE);
    const row = map.get("h1");
    expect(row).toBeDefined();
    expect(row?.externalProjection).toBe(11.2);
    expect(row?.independentProjection).toBe(11.9);
    expect(row?.adjustedProjection).toBe(12.1);
    expect(row?.adjustmentDelta).toBe(0.9);
    expect(row?.adjustmentReasons).toEqual(["positive recent hard-hit trend"]);
  });

  it("independent and external values in the comparison map are never mutated by re-reading", async () => {
    writeJson(`adjusted_projection_snapshots/${DATE}/adjusted_20260813T200000.json`, {
      slate_date: DATE, generated_at: "2026-08-13T20:00:00Z", records: [adjustedRecord()],
    });
    const { getProjectionComparisonByPlayerId } = await import("../externalProjections");
    const first = (await getProjectionComparisonByPlayerId(DATE)).get("h1");
    const second = (await getProjectionComparisonByPlayerId(DATE)).get("h1");
    expect(first).toEqual(second);
  });
});
