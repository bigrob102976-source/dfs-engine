import { describe, expect, it } from "vitest";

import { buildGameEnvironmentReport } from "../environmentTestFixtures";
import type { GameEnvironmentReport, SlateEnvironmentReport, VegasSlateAnalysis } from "../gameEnvironment";
import {
  buildTotalMovementSeries,
  buildVegasAiSummary,
  buildVegasGameRows,
  buildVegasSummaryStats,
  deriveVegasBadges,
  movementPercent,
  movementTone,
  openingImpliedRuns,
  totalTier,
  vegasScore,
} from "../vegasIntelligence";

function game(overrides: Partial<GameEnvironmentReport> = {}): GameEnvironmentReport {
  return buildGameEnvironmentReport(overrides);
}

function analysis(overrides: Partial<VegasSlateAnalysis> = {}): VegasSlateAnalysis {
  return {
    highest_total_game_id: null,
    lowest_total_game_id: null,
    largest_movement_game_id: null,
    biggest_favorite_game_id: null,
    biggest_underdog_game_id: null,
    sharp_movement_game_ids: [],
    ...overrides,
  };
}

describe("totalTier", () => {
  it("mirrors research/game_environment/vegas.py::total_tier thresholds", () => {
    expect(totalTier(9.5)).toBe("high");
    expect(totalTier(10.2)).toBe("high");
    expect(totalTier(7.5)).toBe("low");
    expect(totalTier(6.9)).toBe("low");
    expect(totalTier(8.5)).toBe("medium");
    expect(totalTier(null)).toBe("medium");
  });
});

describe("vegasScore", () => {
  it("mirrors scoring.py::_vegas_component (7.5 -> 0, 9.5+ -> 100)", () => {
    expect(vegasScore(7.5)).toBe(0);
    expect(vegasScore(9.5)).toBe(100);
    expect(vegasScore(8.5)).toBe(50);
    expect(vegasScore(11)).toBe(100); // clamped
    expect(vegasScore(5)).toBe(0); // clamped
    expect(vegasScore(null)).toBeNull();
  });
});

describe("openingImpliedRuns", () => {
  it("recomputes opening implied runs from the SAME formula the mock provider uses for current", () => {
    const vegas = game().vegas!;
    // opening_home: moneyline -120, total 9.0 (favorite gets a larger implied share)
    const { home, away } = openingImpliedRuns(vegas);
    expect(home).not.toBeNull();
    expect(away).not.toBeNull();
    expect(Math.round((home! + away!) * 100) / 100).toBeCloseTo(9.0, 1);
    expect(home!).toBeGreaterThan(away!); // home is the opening favorite (-120)
  });

  it("returns nulls when opening total or moneyline is missing", () => {
    const vegas = { ...game().vegas!, opening_home: { moneyline: null, run_line: null, run_line_odds: null, total: null } };
    expect(openingImpliedRuns(vegas)).toEqual({ home: null, away: null });
  });
});

describe("movementPercent / movementTone", () => {
  it("computes signed percent movement relative to the opening value", () => {
    expect(movementPercent(9.0, 9.7)).toBeCloseTo(7.777, 2);
    expect(movementPercent(-120, -130)).toBeCloseTo(-8.333, 2); // moneyline moved MORE negative -> negative percent
    expect(movementPercent(null, 9.7)).toBeNull();
    expect(movementPercent(0, 5)).toBeNull();
  });

  it("green for positive movement, red for negative, neutral for flat/null", () => {
    expect(movementTone(0.7)).toBe("positive");
    expect(movementTone(-0.7)).toBe("negative");
    expect(movementTone(0)).toBe("neutral");
    expect(movementTone(null)).toBe("neutral");
  });
});

describe("deriveVegasBadges", () => {
  it("tags the slate's highest-total game", () => {
    const g = game({ game_id: "g1" });
    const badges = deriveVegasBadges(g, analysis({ highest_total_game_id: "g1" }));
    expect(badges.map((b) => b.key)).toContain("highestTotal");
  });

  it("tags Sharp Move when in sharp_movement_game_ids and below the steam threshold", () => {
    const g = game({ game_id: "g1", vegas: { ...game().vegas!, total_movement: 1.2 } });
    const badges = deriveVegasBadges(g, analysis({ sharp_movement_game_ids: ["g1"] }));
    expect(badges.map((b) => b.key)).toContain("sharpMove");
    expect(badges.map((b) => b.key)).not.toContain("steamMove");
  });

  it("tags Steam Move instead of Sharp Move once movement crosses the steam threshold", () => {
    const g = game({ game_id: "g1", vegas: { ...game().vegas!, total_movement: 1.8 } });
    const badges = deriveVegasBadges(g, analysis({ sharp_movement_game_ids: ["g1"] }));
    expect(badges.map((b) => b.key)).toContain("steamMove");
    expect(badges.map((b) => b.key)).not.toContain("sharpMove");
  });

  it("tags Trap Game only for the biggest favorite with a falling total", () => {
    const g = game({ game_id: "g1", vegas: { ...game().vegas!, total_movement: -0.6 } });
    const badges = deriveVegasBadges(g, analysis({ biggest_favorite_game_id: "g1" }));
    expect(badges.map((b) => b.key)).toContain("trapGame");
  });

  it("does not tag Trap Game when the total is rising", () => {
    const g = game({ game_id: "g1", vegas: { ...game().vegas!, total_movement: 0.6 } });
    const badges = deriveVegasBadges(g, analysis({ biggest_favorite_game_id: "g1" }));
    expect(badges.map((b) => b.key)).not.toContain("trapGame");
  });

  it("tags Pitcher's Duel for a low total", () => {
    const g = game({ vegas: { ...game().vegas!, current_home: { ...game().vegas!.current_home, total: 7.0 } } });
    const badges = deriveVegasBadges(g, analysis());
    expect(badges.map((b) => b.key)).toContain("pitchersDuel");
  });

  it("tags Home Favorite or Road Favorite based on moneyline sign", () => {
    const homeFav = game({ vegas: { ...game().vegas!, current_home: { ...game().vegas!.current_home, moneyline: -150 }, current_away: { ...game().vegas!.current_away, moneyline: 130 } } });
    expect(deriveVegasBadges(homeFav, analysis()).map((b) => b.key)).toContain("homeFavorite");

    const roadFav = game({ vegas: { ...game().vegas!, current_home: { ...game().vegas!.current_home, moneyline: 130 }, current_away: { ...game().vegas!.current_away, moneyline: -150 } } });
    expect(deriveVegasBadges(roadFav, analysis()).map((b) => b.key)).toContain("roadFavorite");
  });

  it("returns no badges when vegas data is unavailable", () => {
    expect(deriveVegasBadges(game({ vegas: null }), analysis())).toEqual([]);
  });
});

describe("buildVegasAiSummary", () => {
  it("returns an unavailable message when vegas data is missing", () => {
    expect(buildVegasAiSummary(game({ vegas: null }), analysis())).toEqual(["Vegas lines are unavailable for this game."]);
  });

  it("produces deterministic, non-empty bullets for a typical game", () => {
    const summary = buildVegasAiSummary(game(), analysis({ highest_total_game_id: "824238" }));
    expect(summary.length).toBeGreaterThan(0);
    expect(summary).toContain("Highest implied total on the slate.");
  });

  it("mentions bullpen fatigue when a side is fatigued", () => {
    const g = game({ bullpen_away: { ...game().bullpen_away!, estimated_fatigue: "high" } });
    const summary = buildVegasAiSummary(g, analysis());
    expect(summary.some((b) => b.includes("bullpen fatigue"))).toBe(true);
  });

  it("is fully deterministic -- calling twice with the same input produces the same output", () => {
    const g = game();
    expect(buildVegasAiSummary(g, analysis())).toEqual(buildVegasAiSummary(g, analysis()));
  });
});

describe("buildTotalMovementSeries", () => {
  it("returns the opening/current two-point series", () => {
    const series = buildTotalMovementSeries(game().vegas);
    expect(series.points).toEqual([9.0, 9.7]);
    expect(series.open).toBe(9.0);
    expect(series.current).toBe(9.7);
    expect(series.highest).toBe(9.7);
    expect(series.lowest).toBe(9.0);
  });

  it("gracefully returns an empty series when vegas is null", () => {
    const series = buildTotalMovementSeries(null);
    expect(series.points).toEqual([]);
    expect(series.open).toBeNull();
    expect(series.highest).toBeNull();
  });
});

describe("buildVegasSummaryStats", () => {
  function report(games: GameEnvironmentReport[], slateAnalysis: VegasSlateAnalysis | null): SlateEnvironmentReport {
    return { slate_date: "2026-08-13", generated_at: "2026-08-13T18:00:00Z", engine_version: "0.1.0", games, vegas_slate_analysis: slateAnalysis, warnings: [] };
  }

  it("computes Games / Average Total / Highest / Lowest / Biggest Favorite / Largest Moves / Average Implied Runs", () => {
    const g1 = game({ game_id: "g1", home_team: "DET", away_team: "CLE" });
    const g2 = game({
      game_id: "g2",
      home_team: "NYY",
      away_team: "BOS",
      vegas: { ...game().vegas!, game_id: "g2", current_home: { moneyline: -300, run_line: -1.5, run_line_odds: null, total: 11.0 }, current_away: { moneyline: 250, run_line: 1.5, run_line_odds: null, total: 11.0 }, total_movement: -1.5, moneyline_movement_home: -50 },
    });
    const slateAnalysis = analysis({ highest_total_game_id: "g2", lowest_total_game_id: "g1", biggest_favorite_game_id: "g2", largest_movement_game_id: "g2" });
    const stats = buildVegasSummaryStats(report([g1, g2], slateAnalysis));

    expect(stats.gameCount).toBe(2);
    expect(stats.highestTotal.value).toBe(11.0);
    expect(stats.highestTotal.game?.game_id).toBe("g2");
    expect(stats.lowestTotal.value).toBe(9.7);
    expect(stats.biggestFavorite.moneyline).toBe(-300);
    expect(stats.biggestFavorite.team).toBe("NYY");
    expect(stats.largestTotalMove.value).toBe(-1.5);
    expect(stats.largestLineMove.value).toBe(-50);
    expect(stats.averageTotal).toBeCloseTo((9.7 + 11.0) / 2, 5);
  });

  it("never throws and returns nulls for an empty slate", () => {
    const stats = buildVegasSummaryStats(report([], analysis()));
    expect(stats.gameCount).toBe(0);
    expect(stats.averageTotal).toBeNull();
    expect(stats.highestTotal.value).toBeNull();
  });
});

describe("buildVegasGameRows", () => {
  it("joins a probable pitcher by team abbreviation", () => {
    const g = game({ home_team: "DET", away_team: "CLE" });
    const rows = buildVegasGameRows([g], [
      { player_id: "p1", name: "Home Ace", team: "DET", opponent: "CLE", projection: 20, ceiling: 30, overall_score: 80, risk_score: 20, confidence: 80, tags: [], reasons: [] },
      { player_id: "p2", name: "Away Ace", team: "CLE", opponent: "DET", projection: 18, ceiling: 28, overall_score: 75, risk_score: 25, confidence: 75, tags: [], reasons: [] },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].homePitcher?.name).toBe("Home Ace");
    expect(rows[0].awayPitcher?.name).toBe("Away Ace");
  });

  it("leaves pitchers null when no probable starter is found for a team", () => {
    const rows = buildVegasGameRows([game()], []);
    expect(rows[0].homePitcher).toBeNull();
    expect(rows[0].awayPitcher).toBeNull();
  });
});
