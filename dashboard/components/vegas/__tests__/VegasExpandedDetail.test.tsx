import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VegasExpandedDetail } from "../VegasExpandedDetail";
import { buildGameEnvironmentReport } from "@/lib/environmentTestFixtures";
import type { BookLineSnapshot } from "@/lib/gameEnvironment";

function realBooks(): BookLineSnapshot[] {
  return [
    {
      book: "DraftKings",
      home_moneyline: -130,
      away_moneyline: 120,
      total: 9.5,
      total_over_odds: -110,
      total_under_odds: -110,
      home_run_line: -1.5,
      away_run_line: 1.5,
      home_run_line_odds: 145,
      away_run_line_odds: -165,
      last_updated: "2026-08-13T17:00:00Z",
    },
    {
      book: "FanDuel",
      home_moneyline: -125,
      away_moneyline: 115,
      total: 9.0,
      total_over_odds: -105,
      total_under_odds: -115,
      home_run_line: -1.5,
      away_run_line: 1.5,
      home_run_line_odds: 140,
      away_run_line_odds: -160,
      last_updated: "2026-08-13T17:05:00Z",
    },
  ];
}

describe("VegasExpandedDetail", () => {
  it("labels the earlier line 'First Observed', never 'Opening', for the real provider", () => {
    const game = buildGameEnvironmentReport({
      vegas: { ...buildGameEnvironmentReport().vegas!, is_mock: false, provider_name: "SportsGameOdds", books: realBooks(), books_used: ["DraftKings", "FanDuel"] },
    });
    render(<VegasExpandedDetail row={{ game, homePitcher: null, awayPitcher: null }} analysis={null} />);

    expect(screen.getAllByText(/First Observed/).length).toBeGreaterThan(0);
    expect(screen.queryByText("Opening")).not.toBeInTheDocument();
  });

  it("renders a per-book Moneyline/Total/Run Line/Last Updated table and a Market Consensus section for real (non-mock) data", () => {
    const game = buildGameEnvironmentReport({
      vegas: {
        ...buildGameEnvironmentReport().vegas!,
        is_mock: false,
        provider_name: "SportsGameOdds",
        books: realBooks(),
        books_used: ["DraftKings", "FanDuel"],
        consensus_home_win_probability: 0.58,
        consensus_away_win_probability: 0.42,
        implied_runs_calculation_method: "run_line_margin_split",
      },
    });
    render(<VegasExpandedDetail row={{ game, homePitcher: null, awayPitcher: null }} analysis={null} />);

    expect(screen.getByText("Sportsbook Lines")).toBeInTheDocument();
    expect(screen.getByText("DraftKings")).toBeInTheDocument();
    expect(screen.getByText("FanDuel")).toBeInTheDocument();
    expect(screen.getByText("Market Consensus")).toBeInTheDocument();
    expect(screen.getByText("run_line_margin_split", { exact: false })).toBeInTheDocument();
  });

  it("does not render sportsbook/consensus sections for mock data", () => {
    const game = buildGameEnvironmentReport();
    render(<VegasExpandedDetail row={{ game, homePitcher: null, awayPitcher: null }} analysis={null} />);

    expect(screen.queryByText("Sportsbook Lines")).not.toBeInTheDocument();
    expect(screen.queryByText("Market Consensus")).not.toBeInTheDocument();
  });

  it("shows the Pregame Lock comparison when the pregame snapshot is frozen and vegas_live confirms the game left PREGAME", () => {
    const frozenVegas = { ...buildGameEnvironmentReport().vegas!, is_mock: false, is_frozen_pregame: true, vegas_projection_status: "PREGAME_FROZEN" as const };
    const liveVegas = { ...buildGameEnvironmentReport().vegas!, is_mock: false, game_status: "IN_PLAY" as const, current_home: { moneyline: 3300, run_line: 8.5, run_line_odds: null, total: 12.5 } };
    const game = buildGameEnvironmentReport({ vegas: frozenVegas, vegas_live: liveVegas, mlb_game_status: "In Progress", game_status: "IN_PLAY" });

    render(<VegasExpandedDetail row={{ game, homePitcher: null, awayPitcher: null }} analysis={null} marketView="pregame" />);

    expect(screen.getByText("Pregame Lock")).toBeInTheDocument();
    expect(screen.getByText(/NOT USED FOR DFS PROJECTIONS/)).toBeInTheDocument();
    expect(screen.getByText("+3300")).toBeInTheDocument(); // the live/in-play moneyline, shown only in the comparison callout
  });

  it("does not show the Pregame Lock comparison on the Live Market tab (would be redundant)", () => {
    const frozenVegas = { ...buildGameEnvironmentReport().vegas!, is_mock: false, is_frozen_pregame: true, vegas_projection_status: "PREGAME_FROZEN" as const };
    const liveVegas = { ...buildGameEnvironmentReport().vegas!, is_mock: false, game_status: "IN_PLAY" as const };
    const game = buildGameEnvironmentReport({ vegas: frozenVegas, vegas_live: liveVegas, mlb_game_status: "In Progress", game_status: "IN_PLAY" });

    render(<VegasExpandedDetail row={{ game, homePitcher: null, awayPitcher: null }} analysis={null} marketView="live" />);

    expect(screen.queryByText("Pregame Lock")).not.toBeInTheDocument();
  });

  it("shows NO VALID PREGAME VEGAS when vegas is null", () => {
    const game = buildGameEnvironmentReport({ vegas: null });
    render(<VegasExpandedDetail row={{ game, homePitcher: null, awayPitcher: null }} analysis={null} />);
    expect(screen.getByText("NO VALID PREGAME VEGAS")).toBeInTheDocument();
  });
});
