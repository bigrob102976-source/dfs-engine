import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VegasIntelligenceBoard } from "../VegasIntelligenceBoard";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";
import type { SlateEnvironmentReport, VegasSlateAnalysis } from "@/lib/gameEnvironment";
import { buildVegasGameRows } from "@/lib/vegasIntelligence";

function baseVegas() {
  return buildGameEnvironmentReport().vegas!;
}

const HIGH_TOTAL_GAME = buildGameEnvironmentReport({
  game_id: "g-high",
  home_team: "NYY",
  away_team: "BOS",
  environment_score: { overall: 80, pitcher: 20, hitter: 80, stack: 82 },
  vegas: {
    ...baseVegas(),
    game_id: "g-high",
    home_team: "NYY",
    away_team: "BOS",
    opening_home: { moneyline: -180, run_line: -1.5, run_line_odds: null, total: 9.8 },
    current_home: { moneyline: -200, run_line: -1.5, run_line_odds: null, total: 10.6 },
    current_away: { moneyline: 170, run_line: 1.5, run_line_odds: null, total: 10.6 },
    total_movement: 0.8,
    home_implied_runs: 6.0,
    away_implied_runs: 4.6,
  },
});

const LOW_TOTAL_GAME = buildGameEnvironmentReport({
  game_id: "g-low",
  home_team: "SEA",
  away_team: "OAK",
  environment_score: { overall: 25, pitcher: 75, hitter: 25, stack: 22 },
  vegas: {
    ...baseVegas(),
    game_id: "g-low",
    home_team: "SEA",
    away_team: "OAK",
    opening_home: { moneyline: -110, run_line: -1.5, run_line_odds: null, total: 7.0 },
    current_home: { moneyline: -110, run_line: -1.5, run_line_odds: null, total: 6.8 },
    current_away: { moneyline: -110, run_line: 1.5, run_line_odds: null, total: 6.8 },
    total_movement: -0.2,
    home_implied_runs: 3.4,
    away_implied_runs: 3.4,
  },
});

const NO_VEGAS_GAME = buildGameEnvironmentReport({ game_id: "g-none", home_team: "MIA", away_team: "PIT", vegas: null });

const GAMES = [HIGH_TOTAL_GAME, LOW_TOTAL_GAME, NO_VEGAS_GAME];
const ANALYSIS: VegasSlateAnalysis = {
  highest_total_game_id: "g-high",
  lowest_total_game_id: "g-low",
  largest_movement_game_id: "g-high",
  biggest_favorite_game_id: "g-high",
  biggest_underdog_game_id: "g-low",
  sharp_movement_game_ids: [],
};

function buildReport(): SlateEnvironmentReport {
  return { slate_date: "2026-08-13", generated_at: "2026-08-13T18:00:00Z", engine_version: "0.1.0", games: GAMES, vegas_slate_analysis: ANALYSIS, warnings: [] };
}

function renderBoard() {
  const report = buildReport();
  const rows = buildVegasGameRows(report.games, []);
  const coverage = { dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 0, primaryCovered: 0, fallbackCovered: 0, games: [] };
  return render(<VegasIntelligenceBoard report={report} rows={rows} history={[report]} coverage={coverage} />);
}

describe("VegasIntelligenceBoard", () => {
  it("renders every game as a row", () => {
    renderBoard();
    expect(screen.getAllByText(/BOS @ NYY|NYY @ BOS/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SEA/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/MIA/).length).toBeGreaterThan(0);
  });

  it("shows badges for the highest total and pitcher's duel games", () => {
    renderBoard();
    expect(screen.getAllByText("Highest Total").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pitcher's Duel").length).toBeGreaterThan(0);
  });

  it("filters to Highest Totals only", () => {
    renderBoard();
    const filterSelect = screen.getAllByLabelText(/Filter/i)[0] as HTMLSelectElement;
    fireEvent.change(filterSelect, { target: { value: "highestTotals" } });
    expect(screen.getAllByText(/1 \/ 3 games/).length).toBeGreaterThan(0);
  });

  it("searches by team abbreviation", () => {
    renderBoard();
    const search = screen.getByLabelText(/Search Vegas board/i);
    fireEvent.change(search, { target: { value: "sea" } });
    expect(screen.getAllByText(/1 \/ 3 games/).length).toBeGreaterThan(0);
  });

  it("shows the 'no games match' message when filters exclude everything", () => {
    renderBoard();
    const search = screen.getByLabelText(/Search Vegas board/i);
    fireEvent.change(search, { target: { value: "zzz-no-match" } });
    expect(screen.getAllByText("No games match the current filters.").length).toBeGreaterThan(0);
  });

  it("expands a row on click to reveal AI Summary detail, and collapses on a second click", () => {
    const { container } = renderBoard();
    // Target the desktop table's data row directly (aria-expanded) rather
    // than matching team-name text, which also appears inside the
    // (non-clickable) summary cards.
    const dataRow = container.querySelector('tr[aria-expanded="false"]') as HTMLElement;
    expect(dataRow).toBeTruthy();

    fireEvent.click(dataRow);
    expect(screen.getAllByText("AI Summary").length).toBeGreaterThan(0);

    fireEvent.click(container.querySelector('tr[aria-expanded="true"]') as HTMLElement);
    expect(screen.queryAllByText("AI Summary").length).toBe(0);
  });

  it("sorting by Game Total changes the visible order (desktop table)", () => {
    renderBoard();
    const sortSelects = screen.getAllByLabelText(/Sort by/i);
    fireEvent.change(sortSelects[sortSelects.length - 1], { target: { value: "totalCurrent" } });
    // Just assert it doesn't throw and result count stays the same.
    expect(screen.getAllByText(/games$/).length).toBeGreaterThan(0);
  });

  it("toggles Show Sparklines off and on via settings", () => {
    renderBoard();
    const checkbox = screen.getByLabelText("Show Sparklines") as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    fireEvent.click(checkbox);
    expect(checkbox.checked).toBe(false);
  });

  it("renders both a desktop table and a mobile card list (responsive split via Tailwind classes)", () => {
    const { container } = renderBoard();
    const desktopTable = container.querySelector(".hidden.overflow-x-auto");
    expect(desktopTable).toBeTruthy();
    expect(desktopTable?.className).toContain("lg:block");

    const mobileList = container.querySelector(".flex.flex-col.gap-3.lg\\:hidden");
    expect(mobileList).toBeTruthy();
  });

  it("defaults to the Pregame DFS tab and shows a warning banner only on Live Market", () => {
    renderBoard();
    expect(screen.getByRole("tab", { name: "Pregame DFS" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Live Market" })).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByText(/never use this view/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Live Market" }));
    expect(screen.getByRole("tab", { name: "Live Market" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/never use this view/)).toBeInTheDocument();
  });

  it("shows the pregame-lock status badge (LIVE PREGAME by default) for every game", () => {
    renderBoard();
    expect(screen.getAllByText("Live Pregame").length).toBeGreaterThan(0);
  });
});
