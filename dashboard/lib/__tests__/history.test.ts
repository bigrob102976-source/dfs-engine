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
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-dashboard-history-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("buildHistorySeries", () => {
  it("returns an empty array when nothing exists", async () => {
    const { buildHistorySeries } = await import("../history");
    expect(buildHistorySeries()).toEqual([]);
  });

  it("orders points oldest-first", async () => {
    writeJson(path.join(tmpDir, "research_output", "2026-08-11", "slate.json"), { slate_date: "2026-08-11", counts: { games: 15, teams: 0, pitchers: 0, batters: 0 } });
    writeJson(path.join(tmpDir, "research_output", "2026-08-05", "slate.json"), { slate_date: "2026-08-05", counts: { games: 10, teams: 0, pitchers: 0, batters: 0 } });
    const { buildHistorySeries } = await import("../history");
    const series = buildHistorySeries();
    expect(series.map((p) => p.date)).toEqual(["2026-08-05", "2026-08-11"]);
  });

  it("leaves ungenerated fields null instead of zero-filling", async () => {
    writeJson(path.join(tmpDir, "research_output", "2026-08-05", "slate.json"), { slate_date: "2026-08-05", counts: { games: 10, teams: 0, pitchers: 0, batters: 0 } });
    const { buildHistorySeries } = await import("../history");
    const [point] = buildHistorySeries();
    expect(point.games).toBe(10);
    expect(point.pitcherMae).toBeNull();
    expect(point.ownershipMae).toBeNull();
    expect(point.lineupsGenerated).toBeNull();
  });

  it("pulls MAE and correlation from evaluation files when present", async () => {
    writeJson(path.join(tmpDir, "research_output", "2026-08-05", "slate.json"), { slate_date: "2026-08-05", counts: { games: 10, teams: 0, pitchers: 0, batters: 0 } });
    writeJson(path.join(tmpDir, "evaluations", "2026-08-05", "pitcher_evaluation_20260805T180000.json"), {
      slate_metrics: { mae: 8.2, projection_correlation: 0.37 },
    });
    const { buildHistorySeries } = await import("../history");
    const [point] = buildHistorySeries();
    expect(point.pitcherMae).toBe(8.2);
    expect(point.projectionCorrelation).toBe(0.37);
  });
});
