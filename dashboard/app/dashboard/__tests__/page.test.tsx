import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getTodayChicagoDate } from "@/lib/currentDate";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  usePathname: () => "/dashboard",
}));

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let tmpDir: string;
let originalRoot: string | undefined;

beforeEach(async () => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "dfs-command-center-page-"));
  originalRoot = process.env.MLB_DFS_ROOT;
  process.env.MLB_DFS_ROOT = tmpDir;
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ run: null })));
  // AnimatedCounter (KPI cards) animates numeric values in over 600ms via
  // requestAnimationFrame -- stub prefers-reduced-motion so it renders its
  // final value immediately instead of the test racing real animation frames.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  // Milestone 26: TodaysSlatePage now calls resolveSlateContext(), which
  // shells out to scripts/list_dfs_slates.py -- stub the runner so tests
  // never spawn a real Python process.
  const { __setPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __setPythonRunnerForTests(async () => ({
    exitCode: 0,
    stdout: JSON.stringify({
      status: "not_connected", reason: null, provider_name: null, provider_type: null,
      is_mock: false, is_connected: false, source: "unconfigured", slates: [], slates_available: 0,
    }),
    stderr: "",
    command: [],
  }));
});

afterEach(async () => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  fs.rmSync(tmpDir, { recursive: true, force: true });
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  const { __resetPythonRunnerForTests } = await import("@/lib/orchestrator/pythonRunner");
  __resetPythonRunnerForTests();
});

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

// The page itself always resolves "today" via getTodayChicagoDate() with
// no argument (real wall-clock time) -- this fixture must track that
// same value rather than a fixed literal, or it silently stops matching
// once the calendar date advances past whatever day this was written on.
const DATE = getTodayChicagoDate();

function seedEnvironmentReport() {
  writeJson(`game_environment_snapshots/${DATE}/environment_20260814T180000.json`, {
    slate_date: DATE,
    generated_at: "2026-08-14T18:00:00Z",
    engine_version: "0.1.0",
    games: [
      {
        game_id: "g1",
        home_team: "DET",
        away_team: "CLE",
        game_datetime_utc: "2026-08-14T23:10:00Z",
        venue_name: "Comerica Park",
        environment_score: { overall: 70, pitcher: 30, hitter: 70, stack: 74 },
        summary: { headline: "CLE @ DET", bullet_points: ["Balanced offensive environment."] },
        future_adjustment_preview: { weather_points: null, vegas_points: null, bullpen_points: null, enabled: false },
        weather: null,
        weather_analysis: null,
        vegas: {
          game_id: "g1", home_team: "DET", away_team: "CLE", provider_name: "MOCK VEGAS", is_mock: true, retrieved_at: "2026-08-14T18:00:00Z",
          opening_home: { moneyline: -120, run_line: -1.5, run_line_odds: null, total: 9.0 },
          opening_away: { moneyline: 110, run_line: 1.5, run_line_odds: null, total: 9.0 },
          current_home: { moneyline: -130, run_line: -1.5, run_line_odds: null, total: 9.7 },
          current_away: { moneyline: 120, run_line: 1.5, run_line_odds: null, total: 9.7 },
          home_implied_runs: 5.1, away_implied_runs: 4.6, total_movement: 0.7, moneyline_movement_home: -10,
        },
        ballpark: null,
        umpire: { game_id: "g1", status: "UNKNOWN", name: null, strike_percent: null, walk_percent: null, k_percent: null, zone_size_score: null, runs_per_game: null, tendency: "unknown" },
        bullpen_home: null,
        bullpen_away: null,
        travel_home: null,
        travel_away: null,
      },
    ],
    vegas_slate_analysis: {
      highest_total_game_id: "g1", lowest_total_game_id: "g1", largest_movement_game_id: "g1",
      biggest_favorite_game_id: "g1", biggest_underdog_game_id: "g1", sharp_movement_game_ids: [],
    },
    warnings: [],
  });
}

function seedPitcherSnapshot() {
  writeJson(`predictions/${DATE}/pitcher_board_20260814T180000.json`, {
    slate_date: DATE, generated_at_utc: `${DATE}T18:00:00Z`, model_version: "v1", pitcher_count: 1,
    pitchers: [
      { player_id: "p1", name: "Tarik Skubal", team: "DET", opponent: "CLE", game_id: "g1", projection: 24.5, ceiling: 34, overall_score: 92, risk_score: 20, confidence: 90, tags: [], reasons: [] },
    ],
  });
}

function seedAiProjectionSnapshot() {
  writeJson(`ai_projection_snapshots/${DATE}/ai_projection_20260814T190000.json`, {
    slate_date: DATE, generated_at: `${DATE}T19:00:00Z`, model_version: "0.1.0",
    pitcher_snapshot_path: null, batter_snapshot_path: null, player_count: 1, warnings: [],
    players: [
      {
        player_id: "p1", name: "Tarik Skubal", team: "DET", player_type: "pitcher", opponent: "CLE", game_id: "g1",
        salary: 10500, independent_projection: 24.5, independent_ceiling: 34, independent_floor: 18,
        external_projection: null, adjusted_projection: null,
        ai_projection: 26.1, ai_ceiling: 36.2, ai_floor: 19.1, ai_confidence: 88, ai_risk: 22, ai_grade: "A+", ai_value_score: 2.49,
        total_adjustment: 1.6, total_adjustment_percent: 6.53, adjustment_capped: false,
        signals: [{ category: "vegas", label: "Vegas", raw_delta: 0.35, weight: 1, delta: 0.35, reason: "Own team implied 3.2 runs in a low-total game" }],
        reasons: ["Vegas +0.35: Own team implied 3.2 runs in a low-total game"],
        ai_summary: "Tarik Skubal projects to 26.1 AI points (confidence 88, risk 22) with positive Vegas signals.",
        model_version: "0.1.0",
      },
    ],
  });
}

function seedProjectionSourceComparison() {
  writeJson(`evaluations/${DATE}/pitcher_evaluation_20260814T180000.json`, {
    slate_date: DATE, model_version: "0.6.0", generated_at: `${DATE}T18:00:00Z`, snapshot_path: null,
    pitcher_count_predicted: 1,
    slate_metrics: { pitchers_evaluated: 1, mae: 7.54, rmse: 9.1, projection_correlation: 0.4, overall_score_correlation: 0.3 },
    top5_hit_rate: 0.6, top10_hit_rate: 0.6, best_calls: [], worst_calls: [],
    biggest_positive_surprises: [], biggest_busts: [], tag_performance: [], records: [],
  });
  writeJson(`evaluations/${DATE}/projection_source_comparison_20260814T190000.json`, {
    slate_date: DATE, generated_at: `${DATE}T19:00:00+00:00`, actual_result_count: 1,
    sources_present: ["independent", "external", "ai"],
    metrics: [
      { source: "independent", n: 1, mae: 7.54, rmse: 9.1, correlation: 0.4, rank_correlation: 0.42, top5_hit_rate: 0.6, top10_hit_rate: 0.6 },
      { source: "external", n: 1, mae: 7.01, rmse: 8.8, correlation: 0.45, rank_correlation: 0.44, top5_hit_rate: 0.6, top10_hit_rate: 0.7 },
      { source: "ai", n: 1, mae: 6.82, rmse: 8.5, correlation: 0.47, rank_correlation: 0.46, top5_hit_rate: 0.8, top10_hit_rate: 0.7 },
    ],
    ai_vs_independent_mae_improvement_percent: 9.5,
  });
}

describe("TodaysSlatePage (AI Slate Command Center)", () => {
  it("shows a clean empty-data state with no raw script path leaking, when nothing exists yet", async () => {
    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("Today's Slate")).toBeInTheDocument();
    expect(screen.getAllByText("Games").length).toBeGreaterThan(0);
    expect(screen.queryByText(/python /)).not.toBeInTheDocument();
    expect(screen.queryByText(/scripts\//)).not.toBeInTheDocument();
  });

  it("renders real KPI values, the AI Slate Summary, and a clickable Slate Ranking card from a real snapshot", async () => {
    seedEnvironmentReport();
    seedPitcherSnapshot();

    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    // KPI cards animate in via AnimatedCounter (deferred state update on a
    // microtask, see vitest.setup's prefers-reduced-motion stub above) --
    // await the first appearance before asserting. "Highest Total" also
    // appears as this game's own Slate Rankings badge (it IS the slate's
    // highest total), and "9.7" (the game's only total) appears on both
    // the Highest and Lowest Total KPI cards since there's only one game
    // -- assert presence, not uniqueness, for both.
    expect((await screen.findAllByText("Highest Total")).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText("9.7")).length).toBeGreaterThanOrEqual(2);

    // AI Slate Summary (deterministic, no LLM) -- AIInsightBadge prefixes
    // each bullet with a "✦ " icon glyph in the same text node, so match
    // by substring rather than the bullet's exact text.
    expect(screen.getByText(/Today's slate features 1 game\./)).toBeInTheDocument();
    expect(screen.getByText(/Tarik Skubal leads all pitchers\./)).toBeInTheDocument();

    // Slate Rankings card + Game Center expansion -- "CLE @ DET" also
    // appears as the KPI cards' matchup sub-labels and in the Bottom
    // Insights movement lists, so target the Slate Ranking card
    // specifically: it's the only clickable element (a <button>) with
    // this matchup as its accessible name.
    fireEvent.click(screen.getByRole("button", { name: /CLE @ DET/ }));
    expect(screen.getByText("AI Summary")).toBeInTheDocument();

    // Quick Actions
    expect(screen.getByRole("link", { name: "Build Lineups" })).toHaveAttribute("href", "/dashboard/optimizer");
  });

  it("Milestone 20: renders the AI Projection Engine section and Game Center AI data from a real ai_projection snapshot", async () => {
    seedEnvironmentReport();
    seedPitcherSnapshot();
    seedAiProjectionSnapshot();

    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    // Bottom "AI Projection Engine" section -- Tarik Skubal is the only
    // scored player, so he appears in every non-empty AI list (Top AI
    // Values, Largest AI Upgrades, Highest Confidence).
    expect(screen.getByText("AI Projection Engine")).toBeInTheDocument();
    expect(screen.getAllByText("Tarik Skubal").length).toBeGreaterThan(0);
    expect(screen.getByText("Largest AI Downgrades")).toBeInTheDocument(); // header present even though empty

    // Game Center: opening the slide-over shows Top AI Players/Pitchers/Stacks.
    fireEvent.click(screen.getByRole("button", { name: /CLE @ DET/ }));
    expect(screen.getByText("Top AI Players")).toBeInTheDocument();
    expect(screen.getByText("Top AI Pitchers")).toBeInTheDocument();
    expect(screen.getByText("Top AI Stacks")).toBeInTheDocument();
  });

  it("renders the AI Projection Performance card from a real projection_source_comparison snapshot", async () => {
    seedProjectionSourceComparison();

    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    expect(screen.getByText("AI Projection Performance")).toBeInTheDocument();
    const headline = screen.getByText("Overall MAE").parentElement!;
    expect(headline.textContent).toContain("6.82");
    expect(screen.getByText("+9.5%")).toBeInTheDocument();
  });

  it("shows a not-generated message for AI Projection Performance when nothing has been evaluated", async () => {
    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage({ searchParams: Promise.resolve({}) } as never);
    render(jsx);

    // "Recent Accuracy" shares the exact same empty-state phrasing, so
    // this text is intentionally duplicated on the page -- assert
    // presence, not uniqueness.
    expect(screen.getByText("AI Projection Performance")).toBeInTheDocument();
    expect(screen.getAllByText("No evaluated slate yet.").length).toBeGreaterThanOrEqual(1);
  });
});
