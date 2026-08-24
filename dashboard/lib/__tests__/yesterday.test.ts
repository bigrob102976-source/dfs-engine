import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetStorageForTests } from "../storage/getStorage";

let tmpDir: string;

function writeJson(filePath: string, data: unknown) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function pitcherEval(mae: number, corr: number) {
  return {
    slate_date: "x",
    model_version: "0.6.0",
    generated_at: "2026-08-05T18:00:00Z",
    snapshot_path: null,
    pitcher_count_predicted: 30,
    slate_metrics: { pitchers_evaluated: 30, mae, rmse: 10, projection_correlation: corr, overall_score_correlation: 0.3 },
    top5_hit_rate: 0.4,
    top10_hit_rate: 0.5,
    best_calls: [],
    worst_calls: [],
    biggest_positive_surprises: [{ name: "Surprise Pitcher", error: 12.5 }],
    biggest_busts: [{ name: "Bust Pitcher", error: -18.2 }],
    tag_performance: [],
    records: [],
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-dashboard-yesterday-"));
  process.env.MLB_DFS_ROOT = tmpDir;
  __resetStorageForTests();
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  __resetStorageForTests();
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("findLatestEvaluatedDate", () => {
  it("returns null when nothing has been evaluated", async () => {
    const { findLatestEvaluatedDate } = await import("../yesterday");
    expect(await findLatestEvaluatedDate()).toBeNull();
  });

  it("finds the most recent date with a pitcher evaluation", async () => {
    writeJson(path.join(tmpDir, "evaluations", "2026-08-05", "pitcher_evaluation_20260805T180000.json"), pitcherEval(8.2, 0.37));
    const { findLatestEvaluatedDate } = await import("../yesterday");
    expect(await findLatestEvaluatedDate()).toBe("2026-08-05");
  });
});

describe("buildYesterdaySummary", () => {
  it("returns an all-null summary gracefully when nothing has been evaluated", async () => {
    const { buildYesterdaySummary } = await import("../yesterday");
    const summary = await buildYesterdaySummary();
    expect(summary.date).toBeNull();
    expect(summary.pitcherMae).toBeNull();
    expect(summary.trend).toBeNull();
  });

  it("picks the bigger-absolute-error pitcher miss between busts and surprises", async () => {
    writeJson(path.join(tmpDir, "evaluations", "2026-08-05", "pitcher_evaluation_20260805T180000.json"), pitcherEval(8.2, 0.37));
    const { buildYesterdaySummary } = await import("../yesterday");
    const summary = await buildYesterdaySummary();
    expect(summary.pitcherMae).toBe(8.2);
    expect(summary.topProjectionMiss?.name).toBe("Bust Pitcher"); // |-18.2| > |12.5|
  });

  it("computes a trend delta against the prior evaluated slate", async () => {
    writeJson(path.join(tmpDir, "evaluations", "2026-08-05", "pitcher_evaluation_20260805T180000.json"), pitcherEval(10.0, 0.2));
    writeJson(path.join(tmpDir, "evaluations", "2026-08-11", "pitcher_evaluation_20260811T180000.json"), pitcherEval(7.0, 0.5));
    const { buildYesterdaySummary } = await import("../yesterday");
    const summary = await buildYesterdaySummary();
    expect(summary.date).toBe("2026-08-11"); // most recent evaluated date
    expect(summary.priorDate).toBe("2026-08-05");
    expect(summary.trend?.pitcherMaeDelta).toBeCloseTo(-3.0); // improved (lower MAE)
  });

  it("has no trend when there is only one evaluated slate", async () => {
    writeJson(path.join(tmpDir, "evaluations", "2026-08-11", "pitcher_evaluation_20260811T180000.json"), pitcherEval(7.0, 0.5));
    const { buildYesterdaySummary } = await import("../yesterday");
    expect((await buildYesterdaySummary()).trend).toBeNull();
  });
});
