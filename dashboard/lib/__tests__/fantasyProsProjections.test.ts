import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;
const DATE = "2026-08-19";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function fpPlayerRecord(overrides: Record<string, unknown> = {}) {
  return {
    fantasypros_id: "1234",
    name: "Freddie Freeman",
    team: "LAD",
    player_type: "hitter",
    yahoo_id: "5678",
    raw_stats: { pa: 4.5, hrs: 0.31, ave: 0.297 },
    dk_points: 9.85,
    dk_points_breakdown: { single: 2.1, double: 0.9, home_run: 3.1 },
    match_status: "matched",
    match_confidence: "name_team_exact",
    mlb_player_id: "518692",
    candidate_mlb_ids: [],
    candidate_names: [],
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-fantasypros-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestFantasyProsSnapshot", () => {
  it("returns null when no snapshot exists -- never throws", async () => {
    const { loadLatestFantasyProsSnapshot } = await import("../fantasyProsProjections");
    expect(loadLatestFantasyProsSnapshot(DATE)).toBeNull();
  });

  it("returns the latest snapshot by filename timestamp", async () => {
    writeJson(`fantasypros_snapshots/${DATE}/fantasypros_projection_20260819T120000.json`, {
      slate_date: DATE, retrieved_at: "2026-08-19T12:00:00Z", hitter_count: 10, pitcher_count: 10,
      hitters_matched: 1, pitchers_matched: 0, public_api_limited: true, api_tier: "free", players: [],
    });
    writeJson(`fantasypros_snapshots/${DATE}/fantasypros_projection_20260819T150000.json`, {
      slate_date: DATE, retrieved_at: "2026-08-19T15:00:00Z", hitter_count: 10, pitcher_count: 10,
      hitters_matched: 2, pitchers_matched: 0, public_api_limited: true, api_tier: "free", players: [],
    });
    const { loadLatestFantasyProsSnapshot } = await import("../fantasyProsProjections");
    const latest = loadLatestFantasyProsSnapshot(DATE);
    expect(latest?.retrieved_at).toBe("2026-08-19T15:00:00Z");
    expect(latest?.hitters_matched).toBe(2);
  });

  it("never contains an api_key field, regardless of what's on disk", async () => {
    writeJson(`fantasypros_snapshots/${DATE}/fantasypros_projection_20260819T120000.json`, {
      slate_date: DATE, retrieved_at: "2026-08-19T12:00:00Z", hitter_count: 1, pitcher_count: 0,
      hitters_matched: 1, pitchers_matched: 0, public_api_limited: true, api_tier: "free", players: [fpPlayerRecord()],
    });
    const { loadLatestFantasyProsSnapshot } = await import("../fantasyProsProjections");
    const snapshot = loadLatestFantasyProsSnapshot(DATE);
    expect(JSON.stringify(snapshot)).not.toMatch(/api[_-]?key/i);
  });
});

describe("getFantasyProsProjectionByPlayerId", () => {
  it("returns an empty map (never throws) when no snapshot exists", async () => {
    const { getFantasyProsProjectionByPlayerId } = await import("../fantasyProsProjections");
    const map = getFantasyProsProjectionByPlayerId(DATE);
    expect(map.size).toBe(0);
  });

  it("builds a map keyed by mlb_player_id with every field intact, for MATCHED players only", async () => {
    writeJson(`fantasypros_snapshots/${DATE}/fantasypros_projection_20260819T120000.json`, {
      slate_date: DATE, retrieved_at: "2026-08-19T12:00:00Z", hitter_count: 2, pitcher_count: 0,
      hitters_matched: 1, pitchers_matched: 0, public_api_limited: true, api_tier: "free",
      players: [
        fpPlayerRecord(),
        fpPlayerRecord({ fantasypros_id: "9999", name: "Unmatched Guy", mlb_player_id: null, match_status: "unmatched", match_confidence: null }),
      ],
    });
    const { getFantasyProsProjectionByPlayerId } = await import("../fantasyProsProjections");
    const map = getFantasyProsProjectionByPlayerId(DATE);
    expect(map.size).toBe(1);
    const player = map.get("518692");
    expect(player).toBeDefined();
    expect(player?.dk_points).toBe(9.85);
    expect(player?.match_status).toBe("matched");
    expect(map.get("9999")).toBeUndefined();
  });

  it("excludes an ambiguous match even if it happens to carry an mlb_player_id", async () => {
    writeJson(`fantasypros_snapshots/${DATE}/fantasypros_projection_20260819T120000.json`, {
      slate_date: DATE, retrieved_at: "2026-08-19T12:00:00Z", hitter_count: 1, pitcher_count: 0,
      hitters_matched: 0, pitchers_matched: 0, public_api_limited: true, api_tier: "free",
      players: [fpPlayerRecord({ match_status: "ambiguous", mlb_player_id: "518692" })],
    });
    const { getFantasyProsProjectionByPlayerId } = await import("../fantasyProsProjections");
    const map = getFantasyProsProjectionByPlayerId(DATE);
    expect(map.size).toBe(0);
  });
});
