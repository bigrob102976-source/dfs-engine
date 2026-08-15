import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { ProjectionSourceComparisonDocument } from "../projectionSourceComparison";

let tmpDir: string;
const DATE = "2026-08-13";

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

function comparisonDoc(overrides: Partial<ProjectionSourceComparisonDocument> = {}): ProjectionSourceComparisonDocument {
  return {
    slate_date: DATE,
    generated_at: `${DATE}T20:00:00+00:00`,
    actual_result_count: 18,
    sources_present: ["independent", "external", "ai"],
    metrics: [
      { source: "independent", n: 18, mae: 7.54, rmse: 9.1, correlation: 0.4, rank_correlation: 0.42, top5_hit_rate: 0.6, top10_hit_rate: 0.6 },
      { source: "external", n: 18, mae: 7.01, rmse: 8.8, correlation: 0.45, rank_correlation: 0.44, top5_hit_rate: 0.6, top10_hit_rate: 0.7 },
      { source: "ai", n: 18, mae: 6.82, rmse: 8.5, correlation: 0.47, rank_correlation: 0.46, top5_hit_rate: 0.8, top10_hit_rate: 0.7 },
    ],
    ai_vs_independent_mae_improvement_percent: 9.5,
    ...overrides,
  };
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-projection-source-comparison-"));
  process.env.MLB_DFS_ROOT = tmpDir;
});

afterEach(() => {
  delete process.env.MLB_DFS_ROOT;
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("loadLatestProjectionSourceComparison", () => {
  it("returns null when no snapshot exists", async () => {
    const { loadLatestProjectionSourceComparison } = await import("../projectionSourceComparison");
    expect(loadLatestProjectionSourceComparison(DATE)).toBeNull();
  });

  it("returns the latest snapshot by filename timestamp", async () => {
    writeJson(`evaluations/${DATE}/projection_source_comparison_20260813T190000.json`, comparisonDoc({ generated_at: `${DATE}T19:00:00+00:00` }));
    writeJson(`evaluations/${DATE}/projection_source_comparison_20260813T200000.json`, comparisonDoc({ generated_at: `${DATE}T20:00:00+00:00` }));
    const { loadLatestProjectionSourceComparison } = await import("../projectionSourceComparison");
    const latest = loadLatestProjectionSourceComparison(DATE);
    expect(latest?.generated_at).toBe(`${DATE}T20:00:00+00:00`);
  });

  it("does not collide with pitcher_evaluation_ files in the same evaluations/<date> directory", async () => {
    writeJson(`evaluations/${DATE}/pitcher_evaluation_20260813T180000.json`, { slate_date: DATE });
    writeJson(`evaluations/${DATE}/projection_source_comparison_20260813T190000.json`, comparisonDoc());
    const { loadLatestProjectionSourceComparison } = await import("../projectionSourceComparison");
    const latest = loadLatestProjectionSourceComparison(DATE);
    expect(latest?.sources_present).toEqual(["independent", "external", "ai"]);
  });
});

describe("getSourceMetrics", () => {
  it("finds a source's metrics by label", async () => {
    const { getSourceMetrics } = await import("../projectionSourceComparison");
    const doc = comparisonDoc();
    expect(getSourceMetrics(doc, "ai")?.mae).toBe(6.82);
    expect(getSourceMetrics(doc, "independent")?.mae).toBe(7.54);
  });

  it("returns null for a source not present in the document", async () => {
    const { getSourceMetrics } = await import("../projectionSourceComparison");
    expect(getSourceMetrics(comparisonDoc(), "adjusted")).toBeNull();
  });

  it("returns null for a null document", async () => {
    const { getSourceMetrics } = await import("../projectionSourceComparison");
    expect(getSourceMetrics(null, "ai")).toBeNull();
  });
});
