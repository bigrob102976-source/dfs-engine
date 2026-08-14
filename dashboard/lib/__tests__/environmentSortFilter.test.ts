import { describe, expect, it } from "vitest";

import { averageBullpenStrength, filterGamesByPark, parkTier, sortGames, weatherRiskValue } from "../environmentSortFilter";
import { buildGameEnvironmentReport } from "../environmentTestFixtures";

describe("parkTier", () => {
  it("classifies a high park_factor as hitter-friendly", () => {
    const game = buildGameEnvironmentReport({ ballpark: { ...buildGameEnvironmentReport().ballpark!, park_factor: 118 } });
    expect(parkTier(game)).toBe("hitter");
  });

  it("classifies a low park_factor as pitcher-friendly", () => {
    const game = buildGameEnvironmentReport({ ballpark: { ...buildGameEnvironmentReport().ballpark!, park_factor: 85 } });
    expect(parkTier(game)).toBe("pitcher");
  });

  it("classifies a mid park_factor as neutral", () => {
    const game = buildGameEnvironmentReport({ ballpark: { ...buildGameEnvironmentReport().ballpark!, park_factor: 100 } });
    expect(parkTier(game)).toBe("neutral");
  });

  it("returns null when there is no ballpark profile", () => {
    expect(parkTier(buildGameEnvironmentReport({ ballpark: null }))).toBeNull();
  });
});

describe("averageBullpenStrength", () => {
  it("averages home and away strength scores", () => {
    const game = buildGameEnvironmentReport();
    expect(averageBullpenStrength(game)).toBeCloseTo((62.0 + 41.0) / 2);
  });

  it("uses whichever single side is available", () => {
    const game = buildGameEnvironmentReport({ bullpen_away: null });
    expect(averageBullpenStrength(game)).toBeCloseTo(62.0);
  });

  it("returns null when neither side has data", () => {
    const game = buildGameEnvironmentReport({ bullpen_home: null, bullpen_away: null });
    expect(averageBullpenStrength(game)).toBeNull();
  });
});

describe("weatherRiskValue", () => {
  it("returns the larger of delay/postponement risk", () => {
    const game = buildGameEnvironmentReport({
      weather: { ...buildGameEnvironmentReport().weather!, delay_risk_percent: 20, postponement_risk_percent: 60 },
    });
    expect(weatherRiskValue(game)).toBe(60);
  });

  it("returns null when weather is unavailable", () => {
    expect(weatherRiskValue(buildGameEnvironmentReport({ weather: null }))).toBeNull();
  });
});

describe("sortGames", () => {
  const high = buildGameEnvironmentReport({ game_id: "high", environment_score: { overall: 90, pitcher: 10, hitter: 90, stack: 95 } });
  const low = buildGameEnvironmentReport({ game_id: "low", environment_score: { overall: 20, pitcher: 80, hitter: 20, stack: 15 } });
  const missingScoreSignal = buildGameEnvironmentReport({ game_id: "no-vegas", vegas: null });

  it("sorts by score descending", () => {
    const sorted = sortGames([low, high], "score");
    expect(sorted.map((g) => g.game_id)).toEqual(["high", "low"]);
  });

  it("sorts by stack descending", () => {
    const sorted = sortGames([low, high], "stack");
    expect(sorted.map((g) => g.game_id)).toEqual(["high", "low"]);
  });

  it("sorts bullpenRisk ascending (weakest bullpen first)", () => {
    const weak = buildGameEnvironmentReport({
      game_id: "weak",
      bullpen_home: { ...buildGameEnvironmentReport().bullpen_home!, strength_score: 20 },
      bullpen_away: { ...buildGameEnvironmentReport().bullpen_away!, strength_score: 20 },
    });
    const strong = buildGameEnvironmentReport({
      game_id: "strong",
      bullpen_home: { ...buildGameEnvironmentReport().bullpen_home!, strength_score: 80 },
      bullpen_away: { ...buildGameEnvironmentReport().bullpen_away!, strength_score: 80 },
    });
    const sorted = sortGames([strong, weak], "bullpenRisk");
    expect(sorted.map((g) => g.game_id)).toEqual(["weak", "strong"]);
  });

  it("always sorts games with a missing signal to the end, regardless of direction", () => {
    const sorted = sortGames([missingScoreSignal, high], "total");
    expect(sorted.map((g) => g.game_id)).toEqual(["high", "no-vegas"]);
  });
});

describe("filterGamesByPark", () => {
  const hitterPark = buildGameEnvironmentReport({ game_id: "hp", ballpark: { ...buildGameEnvironmentReport().ballpark!, park_factor: 118 } });
  const pitcherPark = buildGameEnvironmentReport({ game_id: "pp", ballpark: { ...buildGameEnvironmentReport().ballpark!, park_factor: 85 } });

  it("returns all games for 'all'", () => {
    expect(filterGamesByPark([hitterPark, pitcherPark], "all")).toHaveLength(2);
  });

  it("filters to only hitter parks", () => {
    expect(filterGamesByPark([hitterPark, pitcherPark], "hitter").map((g) => g.game_id)).toEqual(["hp"]);
  });

  it("filters to only pitcher's parks", () => {
    expect(filterGamesByPark([hitterPark, pitcherPark], "pitcher").map((g) => g.game_id)).toEqual(["pp"]);
  });
});
