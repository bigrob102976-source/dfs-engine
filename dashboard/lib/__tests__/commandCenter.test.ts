import { describe, expect, it } from "vitest";

import {
  buildGameRankings,
  buildLineMovementFeed,
  buildSlateAiSummary,
  buildSlateKpis,
  buildUpcomingLockTimes,
  rankPlayersByValue,
  rankStacksByValue,
  valueScore,
} from "../commandCenter";
import { buildGameEnvironmentReport } from "../environmentTestFixtures";
import type { GameEnvironmentReport, SlateEnvironmentReport } from "../gameEnvironment";
import type { OwnershipSnapshot, PlayerRow, TeamPopularity } from "../types";
import type { StackSummary } from "../stacks";

function baseVegas() {
  return buildGameEnvironmentReport().vegas!;
}

function game(overrides: Partial<GameEnvironmentReport> = {}): GameEnvironmentReport {
  return buildGameEnvironmentReport(overrides);
}

function report(games: GameEnvironmentReport[]): SlateEnvironmentReport {
  const analysis = games.length
    ? {
        highest_total_game_id: games.reduce((best, g) => ((g.vegas?.current_home.total ?? -1) > (best.vegas?.current_home.total ?? -1) ? g : best)).game_id,
        lowest_total_game_id: games.reduce((best, g) => ((g.vegas?.current_home.total ?? 99) < (best.vegas?.current_home.total ?? 99) ? g : best)).game_id,
        largest_movement_game_id: null,
        biggest_favorite_game_id: null,
        biggest_underdog_game_id: null,
        sharp_movement_game_ids: [],
      }
    : null;
  return { slate_date: "2026-08-14", generated_at: "2026-08-14T18:00:00Z", engine_version: "0.1.0", games, vegas_slate_analysis: analysis, warnings: [] };
}

function playerRow(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "p1", playerType: "hitter", name: "Test Player", team: "DET", opponent: "CLE", gameId: "824238",
    position: "OF", positions: ["OF"], battingOrder: 1, salary: 4000, projection: 10, ceiling: 18, floor: 4,
    overall: 60, power: 60, matchup: 60, risk: 30, confidence: 80, ownership: 15, ownershipTier: "mid",
    chalkScore: 50, leverage: 5, tags: [], reasons: [], lineupStatus: null, matchStatus: null, eligibilityStatus: null, optimizerEligible: false, mlProjection: null, mlProjectionStatus: null, raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

function stackSummary(overrides: Partial<StackSummary> = {}): StackSummary {
  return { team: "DET", averageProjection: 10, averageOwnership: 15, teamPopularityScore: 50, averagePower: 60, averageConfidence: 80, confirmedHitterCount: 5, totalHitterCount: 5, status: "CONFIRMED", top5: [], ...overrides };
}

describe("valueScore / rankPlayersByValue / rankStacksByValue", () => {
  it("computes points per $1,000 salary", () => {
    expect(valueScore(playerRow({ projection: 20, salary: 4000 }))).toBeCloseTo(5, 5);
    expect(valueScore(playerRow({ projection: null, salary: 4000 }))).toBeNull();
    expect(valueScore(playerRow({ projection: 20, salary: null }))).toBeNull();
    expect(valueScore(playerRow({ projection: 20, salary: 0 }))).toBeNull();
  });

  it("ranks players descending by value", () => {
    const cheap = playerRow({ id: "cheap", projection: 10, salary: 2000 }); // 5.0 pts/$1k
    const expensive = playerRow({ id: "expensive", projection: 15, salary: 10000 }); // 1.5 pts/$1k
    const ranked = rankPlayersByValue([expensive, cheap]);
    expect(ranked.map((r) => r.id)).toEqual(["cheap", "expensive"]);
  });

  it("derives stack value from top5 average salary, never inventing a salary field on StackSummary", () => {
    const stack = stackSummary({
      team: "DET",
      averageProjection: 10,
      top5: [playerRow({ salary: 4000 }), playerRow({ salary: 6000 })],
    });
    const ranked = rankStacksByValue([stack]);
    expect(ranked[0].value).toBeCloseTo(2, 5); // 10 / 5000 * 1000
  });

  it("gives a null value (never a guess) when a stack's top5 has no salary data", () => {
    const stack = stackSummary({ top5: [] });
    expect(rankStacksByValue([stack])[0].value).toBeNull();
  });
});

describe("buildSlateKpis", () => {
  it("returns 13 KPIs, all null-safe for an empty slate", () => {
    const kpis = buildSlateKpis({ report: report([]), ownership: null, pitcherRows: [], stacks: [] });
    expect(kpis).toHaveLength(13);
    expect(kpis.find((k) => k.key === "games")?.value).toBe(0);
    expect(kpis.every((k) => k.value !== undefined)).toBe(true);
  });

  it("computes Highest/Lowest Total, Best Hitting/Pitching Environment from real games", () => {
    const high = game({ game_id: "high", home_team: "NYY", away_team: "BOS", environment_score: { overall: 80, hitter: 85, pitcher: 15, stack: 82 }, vegas: { ...baseVegas(), game_id: "high", current_home: { ...baseVegas().current_home, total: 11.0 } } });
    const low = game({ game_id: "low", home_team: "SEA", away_team: "OAK", environment_score: { overall: 20, hitter: 15, pitcher: 85, stack: 18 }, vegas: { ...baseVegas(), game_id: "low", current_home: { ...baseVegas().current_home, total: 6.5 } } });
    const kpis = buildSlateKpis({ report: report([high, low]), ownership: null, pitcherRows: [], stacks: [] });

    expect(kpis.find((k) => k.key === "highestTotal")?.value).toBe("11.0");
    expect(kpis.find((k) => k.key === "lowestTotal")?.value).toBe("6.5");
    expect(kpis.find((k) => k.key === "bestHitting")?.sub).toBe("BOS @ NYY");
    expect(kpis.find((k) => k.key === "bestPitching")?.sub).toBe("OAK @ SEA");
  });

  it("computes Highest Owned Stack from ownership.team_popularity", () => {
    const ownership: OwnershipSnapshot = {
      slate_date: "2026-08-14", model_version: "1", player_count: 0, players: [],
      team_popularity: {
        DET: { team: "DET", team_popularity_score: 90, aggregate_projection: 50, top5_projection: 40, hitter_count: 5, aggregate_projected_ownership: 120 } as TeamPopularity,
        CLE: { team: "CLE", team_popularity_score: 30, aggregate_projection: 40, top5_projection: 30, hitter_count: 5, aggregate_projected_ownership: 60 } as TeamPopularity,
      },
      normalization_checks: {},
    };
    const kpis = buildSlateKpis({ report: report([game()]), ownership, pitcherRows: [], stacks: [] });
    expect(kpis.find((k) => k.key === "highestOwnedStack")?.value).toBe("DET");
  });

  it("Top Pitcher / Best Value Pitcher come from pitcherRows", () => {
    const bigProj = playerRow({ id: "big", playerType: "pitcher", name: "Big Proj", projection: 25, salary: 10000 });
    const bestValue = playerRow({ id: "value", playerType: "pitcher", name: "Best Value", projection: 15, salary: 4000 });
    const kpis = buildSlateKpis({ report: report([game()]), ownership: null, pitcherRows: [bigProj, bestValue], stacks: [] });
    expect(kpis.find((k) => k.key === "topPitcher")?.value).toBe("Big Proj");
    expect(kpis.find((k) => k.key === "bestValuePitcher")?.value).toBe("Best Value");
  });
});

describe("buildGameRankings", () => {
  it("sorts games by combined score, descending", () => {
    const strong = game({ game_id: "strong", environment_score: { overall: 90, hitter: 90, pitcher: 10, stack: 90 } });
    const weak = game({ game_id: "weak", environment_score: { overall: 20, hitter: 20, pitcher: 80, stack: 15 } });
    const rankings = buildGameRankings(report([weak, strong]), null);
    expect(rankings.map((r) => r.game.game_id)).toEqual(["strong", "weak"]);
  });

  it("computes Weather Score as the inverse of weather risk", () => {
    const g = game({ weather: { ...buildGameEnvironmentReport().weather!, delay_risk_percent: 30, postponement_risk_percent: 10 } });
    const rankings = buildGameRankings(report([g]), null);
    expect(rankings[0].weatherScore).toBe(70); // 100 - max(30, 10)
  });

  it("reuses environment_score.stack directly as Stack Score", () => {
    const g = game({ environment_score: { overall: 60, hitter: 60, pitcher: 40, stack: 77 } });
    const rankings = buildGameRankings(report([g]), null);
    expect(rankings[0].stackScore).toBe(77);
  });

  it("averages the two teams' team_popularity_score as Ownership Score", () => {
    const g = game({ home_team: "DET", away_team: "CLE" });
    const ownership: OwnershipSnapshot = {
      slate_date: "2026-08-14", model_version: "1", player_count: 0, players: [],
      team_popularity: {
        DET: { team: "DET", team_popularity_score: 60, aggregate_projection: 0, top5_projection: 0, hitter_count: 0, aggregate_projected_ownership: 0 } as TeamPopularity,
        CLE: { team: "CLE", team_popularity_score: 40, aggregate_projection: 0, top5_projection: 0, hitter_count: 0, aggregate_projected_ownership: 0 } as TeamPopularity,
      },
      normalization_checks: {},
    };
    const rankings = buildGameRankings(report([g]), ownership);
    expect(rankings[0].ownershipScore).toBe(50);
  });

  it("tags Wind Out from a weather conclusion code ending in 'out'", () => {
    const g = game({ weather_analysis: { game_id: "824238", conclusions: [{ code: "wind_strong_out", text: "Strong wind blowing out.", favors: "hitter" }] } });
    const rankings = buildGameRankings(report([g]), null);
    expect(rankings[0].badges.map((b) => b.key)).toContain("windOut");
  });

  it("tags Leverage when ownership is low and the stack score is high", () => {
    const g = game({ home_team: "DET", away_team: "CLE", environment_score: { overall: 70, hitter: 70, pitcher: 30, stack: 75 } });
    const ownership: OwnershipSnapshot = {
      slate_date: "2026-08-14", model_version: "1", player_count: 0, players: [],
      team_popularity: {
        DET: { team: "DET", team_popularity_score: 20, aggregate_projection: 0, top5_projection: 0, hitter_count: 0, aggregate_projected_ownership: 0 } as TeamPopularity,
        CLE: { team: "CLE", team_popularity_score: 20, aggregate_projection: 0, top5_projection: 0, hitter_count: 0, aggregate_projected_ownership: 0 } as TeamPopularity,
      },
      normalization_checks: {},
    };
    const rankings = buildGameRankings(report([g]), ownership);
    expect(rankings[0].badges.map((b) => b.key)).toContain("leverage");
  });

  it("never throws for an empty slate", () => {
    expect(buildGameRankings(report([]), null)).toEqual([]);
    expect(buildGameRankings(null, null)).toEqual([]);
  });
});

describe("buildSlateAiSummary", () => {
  it("returns a friendly message for an empty slate rather than an empty list", () => {
    const bullets = buildSlateAiSummary({ report: report([]), ownership: null, pitcherRows: [], hitterRows: [], stacks: [] });
    expect(bullets.length).toBeGreaterThan(0);
    expect(bullets[0]).toMatch(/no slate data/i);
  });

  it("mentions the game count, best hitting team, and top pitcher deterministically", () => {
    const g = game({ home_team: "CHC" });
    const pitcher = playerRow({ id: "p1", playerType: "pitcher", name: "Tarik Skubal", projection: 25 });
    const bullets = buildSlateAiSummary({ report: report([g]), ownership: null, pitcherRows: [pitcher], hitterRows: [], stacks: [] });
    expect(bullets).toContain("Today's slate features 1 game.");
    expect(bullets.some((b) => b.includes("CHC"))).toBe(true);
    expect(bullets).toContain("Tarik Skubal leads all pitchers.");
  });

  it("is fully deterministic -- identical inputs produce identical output", () => {
    const inputs = { report: report([game()]), ownership: null, pitcherRows: [], hitterRows: [], stacks: [] };
    expect(buildSlateAiSummary(inputs)).toEqual(buildSlateAiSummary(inputs));
  });
});

describe("buildLineMovementFeed", () => {
  it("splits games into risers (positive movement) and fallers (negative), and a combined feed sorted by magnitude", () => {
    const up = game({ game_id: "up", vegas: { ...baseVegas(), game_id: "up", total_movement: 0.5 } });
    const down = game({ game_id: "down", vegas: { ...baseVegas(), game_id: "down", total_movement: -1.2 } });
    const flat = game({ game_id: "flat", vegas: { ...baseVegas(), game_id: "flat", total_movement: 0 } });

    const { risers, fallers, feed } = buildLineMovementFeed(report([up, down, flat]));
    expect(risers.map((r) => r.game.game_id)).toEqual(["up"]);
    expect(fallers.map((r) => r.game.game_id)).toEqual(["down"]);
    expect(feed.map((r) => r.game.game_id)).toEqual(["down", "up"]); // |−1.2| > |0.5|
  });
});

describe("buildUpcomingLockTimes", () => {
  it("sorts games chronologically by game_datetime_utc", () => {
    const late = game({ game_id: "late", game_datetime_utc: "2026-08-14T23:10:00Z" });
    const early = game({ game_id: "early", game_datetime_utc: "2026-08-14T17:05:00Z" });
    const entries = buildUpcomingLockTimes(report([late, early]));
    expect(entries.map((e) => e.game.game_id)).toEqual(["early", "late"]);
  });

  it("excludes games with no scheduled time", () => {
    const g = game({ game_datetime_utc: null });
    expect(buildUpcomingLockTimes(report([g]))).toEqual([]);
  });
});
