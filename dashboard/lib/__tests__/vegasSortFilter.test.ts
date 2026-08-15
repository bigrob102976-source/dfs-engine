import { describe, expect, it } from "vitest";

import { buildGameEnvironmentReport } from "../environmentTestFixtures";
import type { GameEnvironmentReport } from "../gameEnvironment";
import { buildVegasGameRows, type VegasGameRow } from "../vegasIntelligence";
import { filterVegasRows, searchVegasRows, sortVegasRows } from "../vegasSortFilter";

function row(overrides: Partial<GameEnvironmentReport> = {}): VegasGameRow {
  return buildVegasGameRows([buildGameEnvironmentReport(overrides)], [])[0];
}

function baseVegas() {
  return buildGameEnvironmentReport().vegas!;
}

describe("sortVegasRows", () => {
  it("sorts by total (descending by default) with nulls last", () => {
    const a = row({ game_id: "a", vegas: { ...baseVegas(), game_id: "a", current_home: { ...baseVegas().current_home, total: 8.0 } } });
    const b = row({ game_id: "b", vegas: { ...baseVegas(), game_id: "b", current_home: { ...baseVegas().current_home, total: 11.0 } } });
    const c = row({ game_id: "c", vegas: null });

    const sorted = sortVegasRows([a, b, c], "totalCurrent", "desc");
    expect(sorted.map((r) => r.game.game_id)).toEqual(["b", "a", "c"]);
  });

  it("sorts ascending when requested", () => {
    const a = row({ game_id: "a", vegas: { ...baseVegas(), current_home: { ...baseVegas().current_home, total: 8.0 } } });
    const b = row({ game_id: "b", vegas: { ...baseVegas(), current_home: { ...baseVegas().current_home, total: 11.0 } } });
    const sorted = sortVegasRows([a, b], "totalCurrent", "asc");
    expect(sorted.map((r) => r.game.game_id)).toEqual(["a", "b"]);
  });

  it("sorts totalMovement by magnitude when descending -- biggest swing first regardless of direction", () => {
    const up = row({ game_id: "up", vegas: { ...baseVegas(), total_movement: 0.5 } });
    const down = row({ game_id: "down", vegas: { ...baseVegas(), total_movement: -1.8 } });
    const flat = row({ game_id: "flat", vegas: { ...baseVegas(), total_movement: 0.1 } });
    const sorted = sortVegasRows([up, down, flat], "totalMovement", "desc");
    expect(sorted.map((r) => r.game.game_id)).toEqual(["down", "up", "flat"]);
  });

  it("is stable for equal values (preserves original order)", () => {
    const a = row({ game_id: "a" });
    const b = row({ game_id: "b" });
    const sorted = sortVegasRows([a, b], "environmentScore", "desc");
    expect(sorted.map((r) => r.game.game_id)).toEqual(["a", "b"]);
  });
});

describe("filterVegasRows", () => {
  const high = row({ game_id: "high", vegas: { ...baseVegas(), current_home: { ...baseVegas().current_home, total: 10.5 } } });
  const low = row({ game_id: "low", vegas: { ...baseVegas(), current_home: { ...baseVegas().current_home, total: 6.5 } } });
  const noVegas = row({ game_id: "none", vegas: null });

  it("'all' returns every row", () => {
    expect(filterVegasRows([high, low, noVegas], "all")).toHaveLength(3);
  });

  it("'gameTotal' excludes games with no Vegas total", () => {
    const result = filterVegasRows([high, low, noVegas], "gameTotal");
    expect(result.map((r) => r.game.game_id)).toEqual(["high", "low"]);
  });

  it("'highestTotals' / 'lowestTotals' use the same thresholds as total_tier", () => {
    expect(filterVegasRows([high, low], "highestTotals").map((r) => r.game.game_id)).toEqual(["high"]);
    expect(filterVegasRows([high, low], "lowestTotals").map((r) => r.game.game_id)).toEqual(["low"]);
  });

  it("'largestMoves' keeps only games at/above the sharp movement threshold", () => {
    const moved = row({ game_id: "moved", vegas: { ...baseVegas(), total_movement: 1.2 } });
    const flat = row({ game_id: "flat", vegas: { ...baseVegas(), total_movement: 0.2 } });
    expect(filterVegasRows([moved, flat], "largestMoves").map((r) => r.game.game_id)).toEqual(["moved"]);
  });

  it("'sharpMoney' keeps only games with notable moneyline movement", () => {
    const moved = row({ game_id: "moved", vegas: { ...baseVegas(), moneyline_movement_home: -25 } });
    const flat = row({ game_id: "flat", vegas: { ...baseVegas(), moneyline_movement_home: -5 } });
    expect(filterVegasRows([moved, flat], "sharpMoney").map((r) => r.game.game_id)).toEqual(["moved"]);
  });

  it("'highestImplied' / 'lowestImplied' key off either team's implied runs", () => {
    const highImplied = row({ game_id: "hi", vegas: { ...baseVegas(), home_implied_runs: 6.0, away_implied_runs: 3.5 } });
    const lowImplied = row({ game_id: "lo", vegas: { ...baseVegas(), home_implied_runs: 2.5, away_implied_runs: 2.8 } });
    expect(filterVegasRows([highImplied, lowImplied], "highestImplied").map((r) => r.game.game_id)).toEqual(["hi"]);
    expect(filterVegasRows([highImplied, lowImplied], "lowestImplied").map((r) => r.game.game_id)).toEqual(["lo"]);
  });
});

describe("searchVegasRows", () => {
  it("matches by home or away team abbreviation, case-insensitively", () => {
    const rows = [row({ home_team: "DET", away_team: "CLE" })];
    expect(searchVegasRows(rows, "det")).toHaveLength(1);
    expect(searchVegasRows(rows, "cle")).toHaveLength(1);
    expect(searchVegasRows(rows, "nyy")).toHaveLength(0);
  });

  it("matches by probable pitcher name", () => {
    const rows = buildVegasGameRows(
      [buildGameEnvironmentReport({ home_team: "DET", away_team: "CLE" })],
      [{ player_id: "p1", name: "Home Ace", team: "DET", opponent: "CLE", projection: 20, ceiling: 30, overall_score: 80, risk_score: 20, confidence: 80, tags: [], reasons: [] }],
    );
    expect(searchVegasRows(rows, "home ace")).toHaveLength(1);
    expect(searchVegasRows(rows, "nobody")).toHaveLength(0);
  });

  it("returns all rows for an empty/whitespace query", () => {
    const rows = [row()];
    expect(searchVegasRows(rows, "")).toHaveLength(1);
    expect(searchVegasRows(rows, "   ")).toHaveLength(1);
  });
});
