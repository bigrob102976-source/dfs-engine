import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { __resetStorageForTests } from "@/lib/storage/getStorage";

let originalRoot: string | undefined;
let tmpDir: string | undefined;

beforeEach(() => {
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = "C:\\nonexistent-dfs-root-for-yesterday-page-test";
  __resetStorageForTests();
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  __resetStorageForTests();
  if (tmpDir) {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    tmpDir = undefined;
  }
});

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir!, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

describe("YesterdayPage (no evaluated slate -- historical/read-only)", () => {
  it("shows a plain unavailable message with no developer command and no generate button", async () => {
    const YesterdayPage = (await import("../page")).default;
    render(await YesterdayPage());

    expect(screen.getByText("Historical data unavailable for this slate.")).toBeInTheDocument();
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Run:/)).not.toBeInTheDocument();
    // Historical pages must not offer a rebuild action unless explicitly supported.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("YesterdayPage (Milestone: Projection Source Performance table)", () => {
  const DATE = "2026-08-13";

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-yesterday-page-comparison-"));
    process.env.MLB_DFS_ROOT = tmpDir;
    __resetStorageForTests();
  });

  it("renders the per-source breakdown table from a real comparison snapshot", async () => {
    writeJson(`evaluations/${DATE}/pitcher_evaluation_20260813T180000.json`, {
      slate_date: DATE, model_version: "0.6.0", generated_at: `${DATE}T18:00:00Z`, snapshot_path: null,
      pitcher_count_predicted: 18,
      slate_metrics: { pitchers_evaluated: 18, mae: 7.54, rmse: 9.1, projection_correlation: 0.4, overall_score_correlation: 0.3 },
      top5_hit_rate: 0.6, top10_hit_rate: 0.6, best_calls: [], worst_calls: [],
      biggest_positive_surprises: [], biggest_busts: [], tag_performance: [], records: [],
    });
    writeJson(`evaluations/${DATE}/projection_source_comparison_20260813T190000.json`, {
      slate_date: DATE, generated_at: `${DATE}T19:00:00+00:00`, actual_result_count: 18,
      sources_present: ["independent", "external", "ai"],
      metrics: [
        { source: "independent", n: 18, mae: 7.54, rmse: 9.1, correlation: 0.4, rank_correlation: 0.42, top5_hit_rate: 0.6, top10_hit_rate: 0.6 },
        { source: "external", n: 18, mae: 7.01, rmse: 8.8, correlation: 0.45, rank_correlation: 0.44, top5_hit_rate: 0.6, top10_hit_rate: 0.7 },
        { source: "ai", n: 18, mae: 6.82, rmse: 8.5, correlation: 0.47, rank_correlation: 0.46, top5_hit_rate: 0.8, top10_hit_rate: 0.7 },
      ],
      ai_vs_independent_mae_improvement_percent: 9.5,
    });

    const YesterdayPage = (await import("../page")).default;
    render(await YesterdayPage());

    expect(screen.getByText("Projection Source Performance")).toBeInTheDocument();
    const table = screen.getByText("Projection Source Performance").closest("div")!.parentElement!;
    expect(table.textContent).toContain("Legacy");
    expect(table.textContent).toContain("7.54");
    expect(table.textContent).toContain("BlueCollar");
    expect(table.textContent).toContain("7.01");
    expect(table.textContent).toContain("Big Money AI");
    expect(table.textContent).toContain("6.82");
    expect(screen.getByText("+9.5%")).toBeInTheDocument();
  });

  it("omits the table entirely when no comparison snapshot exists for the evaluated date", async () => {
    writeJson(`evaluations/${DATE}/pitcher_evaluation_20260813T180000.json`, {
      slate_date: DATE, model_version: "0.6.0", generated_at: `${DATE}T18:00:00Z`, snapshot_path: null,
      pitcher_count_predicted: 18,
      slate_metrics: { pitchers_evaluated: 18, mae: 7.54, rmse: 9.1, projection_correlation: 0.4, overall_score_correlation: 0.3 },
      top5_hit_rate: 0.6, top10_hit_rate: 0.6, best_calls: [], worst_calls: [],
      biggest_positive_surprises: [], biggest_busts: [], tag_performance: [], records: [],
    });

    const YesterdayPage = (await import("../page")).default;
    render(await YesterdayPage());

    expect(screen.queryByText("Projection Source Performance")).not.toBeInTheDocument();
  });
});
