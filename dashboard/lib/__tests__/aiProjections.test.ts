import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

let tmpDir: string;
const DATE = "2026-08-14";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function aiPlayerRecord(overrides: Record<string, unknown> = {}) {
  return {
    player_id: "519242",
    name: "Chris Sale",
    team: "ATL",
    player_type: "pitcher",
    opponent: "AZ",
    game_id: "824882",
    salary: 10700,
    independent_projection: 26.1,
    independent_ceiling: 34.1,
    independent_floor: 21.5,
    external_projection: null,
    adjusted_projection: null,
    ai_projection: 27.4,
    ai_ceiling: 35.8,
    ai_floor: 22.6,
    ai_confidence: 81.2,
    ai_risk: 35.0,
    ai_grade: "A+",
    ai_value_score: 2.56,
    total_adjustment: 1.3,
    total_adjustment_percent: 4.98,
    adjustment_capped: false,
    signals: [{ category: "vegas", label: "Vegas", raw_delta: 0.37, weight: 1.0, delta: 0.37, reason: "Own team implied 5.0 runs" }],
    reasons: ["Vegas +0.37: Own team implied 5.0 runs"],
    ai_summary: "Chris Sale projects to 27.4 AI points (confidence 81, risk 35) with positive Vegas signals.",
    model_version: "0.1.0",
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-aiprojections-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestAiProjectionSnapshot", () => {
  it("returns null when no snapshot exists", async () => {
    const { loadLatestAiProjectionSnapshot } = await import("../aiProjections");
    expect(loadLatestAiProjectionSnapshot(DATE)).toBeNull();
  });

  it("returns the latest snapshot by filename timestamp", async () => {
    writeJson(`ai_projection_snapshots/${DATE}/ai_projection_20260814T180000.json`, {
      slate_date: DATE, generated_at: "2026-08-14T18:00:00Z", model_version: "0.1.0", player_count: 0, players: [], warnings: [],
    });
    writeJson(`ai_projection_snapshots/${DATE}/ai_projection_20260814T190000.json`, {
      slate_date: DATE, generated_at: "2026-08-14T19:00:00Z", model_version: "0.1.0", player_count: 0, players: [], warnings: [],
    });
    const { loadLatestAiProjectionSnapshot } = await import("../aiProjections");
    const latest = loadLatestAiProjectionSnapshot(DATE);
    expect(latest?.generated_at).toBe("2026-08-14T19:00:00Z");
  });
});

describe("getAiProjectionByPlayerId", () => {
  it("returns an empty map (never throws) when no snapshot exists", async () => {
    const { getAiProjectionByPlayerId } = await import("../aiProjections");
    const map = getAiProjectionByPlayerId(DATE);
    expect(map.size).toBe(0);
  });

  it("builds a map keyed by player_id with every AI field intact", async () => {
    writeJson(`ai_projection_snapshots/${DATE}/ai_projection_20260814T180000.json`, {
      slate_date: DATE, generated_at: "2026-08-14T18:00:00Z", model_version: "0.1.0",
      player_count: 1, players: [aiPlayerRecord()], warnings: [],
    });
    const { getAiProjectionByPlayerId } = await import("../aiProjections");
    const map = getAiProjectionByPlayerId(DATE);
    const player = map.get("519242");
    expect(player).toBeDefined();
    expect(player?.ai_projection).toBe(27.4);
    expect(player?.ai_grade).toBe("A+");
    expect(player?.ai_confidence).toBe(81.2);
    expect(player?.signals).toHaveLength(1);
    expect(player?.reasons[0]).toContain("Vegas +0.37");
  });
});
