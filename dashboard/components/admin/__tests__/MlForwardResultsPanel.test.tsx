import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

import { MlForwardResultsPanel } from "../MlForwardResultsPanel";
import type { MlForwardResultsDocument } from "@/lib/mlForwardResultsTypes";

afterEach(() => {
  vi.unstubAllGlobals();
});

function baseDoc(overrides: Partial<MlForwardResultsDocument> = {}): MlForwardResultsDocument {
  const pitchers = [{ player_id: "1", name: "Pitcher A", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "pitcher" as const, projection_source: "big_money_ml", pregame_projection: 20.0, actual_dk: 22.0, error: 2.0, absolute_error: 2.0 }];
  const hitters = [
    { player_id: "2", name: "Hitter A", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "hitter" as const, projection_source: "big_money_ml", pregame_projection: 10.0, actual_dk: 14.0, error: 4.0, absolute_error: 4.0 },
    { player_id: "2", name: "Hitter A", team: "NYY", opponent: "BOS", game_id: "g1", player_type: "hitter" as const, projection_source: "native", pregame_projection: 8.0, actual_dk: 14.0, error: 6.0, absolute_error: 6.0 },
  ];
  return {
    slate_date: "2026-08-22", slate_id: "dkunofficial-152547", generated_at: "2026-08-22T23:59:00+00:00",
    games_total: 3, games_final: 3, all_final: true,
    games: [{ game_id: "g1", detailed_state: "Final", final: true }],
    players_graded: 60, ml_pitchers_graded: 6, ml_hitters_graded: 54, lineups_graded: 20,
    player_grading: { pitchers, hitters, combined: [...pitchers, ...hitters] },
    lineup_grading: {
      projection_source: "big_money_ml", lineup_sets_found: 1, lineups_total: 1, lineups_fully_graded: 1,
      lineups: [{
        lineup_index: 1, salary: 45000, projected: 100.0, actual: 105.5, difference: 5.5, fully_graded: true, missing_players: [],
        players: [{ name: "Hitter A", mlb_player_id: "2", slot: "OF", projection: 10.0, actual_dk: 14.0, difference: 4.0 }],
      }],
      highest_actual: 105.5, lowest_actual: 105.5, average_actual: 105.5, average_projected: 100.0, average_projection_error: 5.5,
    },
    lineup_source_comparison: {},
    source_comparison: {
      pitchers: { slates_requested: 1, slates_with_actual_results: 1, source_metrics: [{ source: "big_money_ml", shared_sample_n: 6, dates_included: 1, mae: 3.2, rmse: 4.1, pearson: 0.8, spearman: 0.7, avg_top5_hit_rate: 0.6, avg_top10_hit_rate: 0.5 }] },
      hitters: { slates_requested: 1, slates_with_actual_results: 1, source_metrics: [{ source: "big_money_ml", shared_sample_n: 54, dates_included: 1, mae: 4.5, rmse: 5.9, pearson: 0.75, spearman: 0.68, avg_top5_hit_rate: 0.4, avg_top10_hit_rate: 0.35 }] },
      combined: { slates_requested: 1, slates_with_actual_results: 1, source_metrics: [] },
    },
    ceiling_monitor: { dates_with_ceiling_events: 1, thresholds: { "20.0": { n: 2, avg_predicted: 15.0, avg_actual: 25.0, bias: -10.0 } } },
    zero_game_monitor: { n: 3, dates_with_zero_games: 1, avg_predicted: 6.0, bias: 6.0, mae: 6.0 },
    disaster_pitcher_monitor: { n: 1, threshold: 2.0, dates_with_disaster_starts: 1, bias: 10.0, mae: 10.0 },
    ...overrides,
  };
}

describe("MlForwardResultsPanel", () => {
  it("shows a collect-results prompt when no document exists yet", () => {
    render(<MlForwardResultsPanel date="2026-08-22" slateId="dkunofficial-152547" document={null} />);
    expect(screen.getByText(/No forward-results document collected yet/)).toBeInTheDocument();
    expect(screen.getByText("Collect Results")).toBeInTheDocument();
  });

  it("shows SLATE RESULTS metrics from the document", () => {
    render(<MlForwardResultsPanel date="2026-08-22" slateId="dkunofficial-152547" document={baseDoc()} />);
    expect(screen.getByText("152547")).toBeInTheDocument();
    expect(screen.getByText("3/3")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("shows a PARTIAL RESULTS banner when the slate isn't fully final", () => {
    render(<MlForwardResultsPanel date="2026-08-22" slateId="dkunofficial-152547" document={baseDoc({ games_final: 1, all_final: false })} />);
    expect(screen.getByText(/PARTIAL RESULTS/)).toBeInTheDocument();
  });

  it("switches PROJECTION PERFORMANCE tabs between hitters/pitchers/combined", () => {
    render(<MlForwardResultsPanel date="2026-08-22" slateId="dkunofficial-152547" document={baseDoc()} />);
    // hitters tab is the default
    expect(screen.getByText("4.50")).toBeInTheDocument(); // hitter MAE
    fireEvent.click(screen.getByRole("tab", { name: "pitchers" }));
    expect(screen.getByText("3.20")).toBeInTheDocument(); // pitcher MAE
  });

  it("shows the Big Money ML Lineups table with highest/average/lowest actual", () => {
    render(<MlForwardResultsPanel date="2026-08-22" slateId="dkunofficial-152547" document={baseDoc()} />);
    expect(screen.getAllByText("105.50").length).toBeGreaterThan(0);
    expect(screen.getByText("45000")).toBeInTheDocument();
  });

  it("shows Model Disagreements pivoted by player", () => {
    render(<MlForwardResultsPanel date="2026-08-22" slateId="dkunofficial-152547" document={baseDoc()} />);
    expect(screen.getByText("Hitter A")).toBeInTheDocument();
  });

  it("shows Known ML Monitors sections", () => {
    render(<MlForwardResultsPanel date="2026-08-22" slateId="dkunofficial-152547" document={baseDoc()} />);
    expect(screen.getByText("Zero-Game Monitor")).toBeInTheDocument();
    expect(screen.getByText(/Disaster Pitcher Monitor/)).toBeInTheDocument();
  });
});
