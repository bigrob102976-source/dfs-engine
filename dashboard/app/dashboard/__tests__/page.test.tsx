import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  usePathname: () => "/dashboard",
}));

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

let tmpDir: string;
let originalRoot: string | undefined;

beforeEach(() => {
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
});

afterEach(() => {
  if (originalRoot === undefined) delete process.env.MLB_DFS_ROOT;
  else process.env.MLB_DFS_ROOT = originalRoot;
  fs.rmSync(tmpDir, { recursive: true, force: true });
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function writeJson(relPath: string, data: unknown) {
  const filePath = path.join(tmpDir, relPath);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data));
}

const DATE = "2026-08-14";

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

describe("TodaysSlatePage (AI Slate Command Center)", () => {
  it("shows a clean empty-data state with no raw script path leaking, when nothing exists yet", async () => {
    const TodaysSlatePage = (await import("../page")).default;
    const jsx = await TodaysSlatePage();
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
    const jsx = await TodaysSlatePage();
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
});
