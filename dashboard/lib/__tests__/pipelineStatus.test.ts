import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;

function writeJson(filePath: string, data: unknown) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-dashboard-root-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("buildPipelineStatuses", () => {
  it("returns an empty array when there is no known slate date", async () => {
    const { buildPipelineStatuses } = await import("../pipelineStatus");
    expect(buildPipelineStatuses(null)).toEqual([]);
  });

  it("marks every stage missing when nothing has been generated", async () => {
    writeJson(path.join(tmpDir, "research_output", "2026-08-11", "slate.json"), {
      slate_date: "2026-08-11",
      counts: { games: 10, teams: 20, pitchers: 30, batters: 100 },
    });
    const { buildPipelineStatuses } = await import("../pipelineStatus");
    const statuses = buildPipelineStatuses("2026-08-11");
    const byLabel = Object.fromEntries(statuses.map((s) => [s.label, s]));
    expect(byLabel["Research Package"].state).toBe("ready");
    expect(byLabel["Pitcher Snapshot"].state).toBe("missing");
    expect(byLabel["Ownership"].state).toBe("missing");
    expect(byLabel["Ownership"].helpCommand).toContain("project_dk_ownership.py");
  });

  it("marks a ready stage outdated when generated before its upstream dependency", async () => {
    writeJson(path.join(tmpDir, "dfs_input", "2026-08-11", "dk_player_pool_20260811T200000.json"), {
      slate_date: "2026-08-11",
      generated_at_utc: "2026-08-11T20:00:00+00:00",
      player_count: 0,
      players: [],
    });
    writeJson(path.join(tmpDir, "ownership_predictions", "2026-08-11", "ownership_20260811T180000.json"), {
      slate_date: "2026-08-11",
      generated_at_utc: "2026-08-11T18:00:00+00:00",
      model_version: "0.1.0",
      player_count: 0,
      players: [],
      team_popularity: {},
      normalization_checks: {},
    });
    const { buildPipelineStatuses } = await import("../pipelineStatus");
    const statuses = buildPipelineStatuses("2026-08-11");
    const ownership = statuses.find((s) => s.label === "Ownership")!;
    expect(ownership.state).toBe("outdated");
  });

  it("marks ownership ready when generated after the DK pool it used", async () => {
    writeJson(path.join(tmpDir, "dfs_input", "2026-08-11", "dk_player_pool_20260811T180000.json"), {
      slate_date: "2026-08-11",
      generated_at_utc: "2026-08-11T18:00:00+00:00",
      player_count: 0,
      players: [],
    });
    writeJson(path.join(tmpDir, "ownership_predictions", "2026-08-11", "ownership_20260811T200000.json"), {
      slate_date: "2026-08-11",
      generated_at_utc: "2026-08-11T20:00:00+00:00",
      model_version: "0.1.0",
      player_count: 0,
      players: [],
      team_popularity: {},
      normalization_checks: {},
    });
    const { buildPipelineStatuses } = await import("../pipelineStatus");
    const statuses = buildPipelineStatuses("2026-08-11");
    const ownership = statuses.find((s) => s.label === "Ownership")!;
    expect(ownership.state).toBe("ready");
  });
});

describe("buildSlateSummary", () => {
  it("returns zeros when there is no slate date", async () => {
    const { buildSlateSummary } = await import("../pipelineStatus");
    expect(buildSlateSummary(null)).toEqual({
      gamesOnResearch: 0,
      gamesOnDkSlate: null,
      postedLineupGames: 0,
      missingLineupGames: 0,
    });
  });

  it("computes posted vs. missing lineup games from the batter snapshot", async () => {
    writeJson(path.join(tmpDir, "research_output", "2026-08-11", "slate.json"), {
      slate_date: "2026-08-11",
      counts: { games: 10, teams: 20, pitchers: 30, batters: 100 },
    });
    writeJson(path.join(tmpDir, "predictions", "2026-08-11", "batter_board_20260811T180000.json"), {
      slate_date: "2026-08-11",
      generated_at_utc: "2026-08-11T18:00:00+00:00",
      model_version: "0.1.0",
      hitter_count: 2,
      missing_lineup_game_ids: ["g9", "g10"],
      hitters: [
        { player_id: "1", name: "A", team: "AAA", opponent: "BBB", game_id: "g1", batting_order: 1, projection: 8, ceiling: 15, overall_score: 60, risk_score: 30, confidence: 90, tags: [], reasons: [] },
        { player_id: "2", name: "B", team: "CCC", opponent: "DDD", game_id: "g2", batting_order: 1, projection: 8, ceiling: 15, overall_score: 60, risk_score: 30, confidence: 90, tags: [], reasons: [] },
      ],
    });
    const { buildSlateSummary } = await import("../pipelineStatus");
    const summary = buildSlateSummary("2026-08-11");
    expect(summary.gamesOnResearch).toBe(10);
    expect(summary.postedLineupGames).toBe(2);
    expect(summary.missingLineupGames).toBe(2);
  });
});
