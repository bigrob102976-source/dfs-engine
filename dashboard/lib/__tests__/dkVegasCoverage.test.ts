import { describe, expect, it } from "vitest";

import { buildGameEnvironmentReport } from "../environmentTestFixtures";
import { buildDkSlateVegasCoverage } from "../dkVegasCoverage";
import type { SlateEnvironmentReport } from "../gameEnvironment";

function report(games: ReturnType<typeof buildGameEnvironmentReport>[]): SlateEnvironmentReport {
  return { slate_date: "2026-08-17", generated_at: "2026-08-17T18:00:00Z", engine_version: "0.1.0", games, vegas_slate_analysis: null, warnings: [] };
}

function matchReport(matches: Record<string, unknown>): Record<string, unknown> {
  return { dk_game_matches: matches };
}

describe("buildDkSlateVegasCoverage", () => {
  it("returns empty coverage when the match report is null", () => {
    const coverage = buildDkSlateVegasCoverage(null, null);
    expect(coverage.dkGames).toBe(0);
    expect(coverage.coveragePercent).toBe(0);
    expect(coverage.games).toEqual([]);
  });

  it("scopes the denominator to DK slate games, not the environment report's game count", () => {
    const g1 = buildGameEnvironmentReport({ game_id: "g1", home_team: "DET", away_team: "CLE" });
    const g2 = buildGameEnvironmentReport({ game_id: "g2", home_team: "NYY", away_team: "BOS" });
    const g3ExtraNotOnDk = buildGameEnvironmentReport({ game_id: "g3", home_team: "SEA", away_team: "OAK" });
    const env = report([g1, g2, g3ExtraNotOnDk]);
    const mr = matchReport({
      "CLE@DET 07:05PM ET": { status: "matched", research_game_id: "g1", dk_away: "CLE", dk_home: "DET" },
      "BOS@NYY 07:05PM ET": { status: "matched", research_game_id: "g2", dk_away: "BOS", dk_home: "NYY" },
    });

    const coverage = buildDkSlateVegasCoverage(mr, env);
    expect(coverage.dkGames).toBe(2); // NOT 3 -- g3 isn't on the DK slate
  });

  it("counts LIVE_PREGAME and PREGAME_FROZEN as covered", () => {
    const live = buildGameEnvironmentReport({ game_id: "g1", vegas: { ...buildGameEnvironmentReport().vegas!, vegas_projection_status: "LIVE_PREGAME" } });
    const frozen = buildGameEnvironmentReport({ game_id: "g2", vegas: { ...buildGameEnvironmentReport().vegas!, vegas_projection_status: "PREGAME_FROZEN", is_frozen_pregame: true } });
    const env = report([live, frozen]);
    const mr = matchReport({
      a: { status: "matched", research_game_id: "g1", dk_away: "CLE", dk_home: "DET" },
      b: { status: "matched", research_game_id: "g2", dk_away: "BOS", dk_home: "NYY" },
    });

    const coverage = buildDkSlateVegasCoverage(mr, env);
    expect(coverage.pregameCovered).toBe(2);
    expect(coverage.frozen).toBe(1);
    expect(coverage.coveragePercent).toBe(100);
  });

  it("counts IN_PLAY_ONLY games as in-play ignored, not covered", () => {
    const inPlay = buildGameEnvironmentReport({
      game_id: "g1",
      vegas: { ...buildGameEnvironmentReport().vegas!, vegas_projection_status: "IN_PLAY_ONLY", home_implied_runs: null, away_implied_runs: null },
    });
    const env = report([inPlay]);
    const mr = matchReport({ a: { status: "matched", research_game_id: "g1", dk_away: "CLE", dk_home: "DET" } });

    const coverage = buildDkSlateVegasCoverage(mr, env);
    expect(coverage.inPlayIgnored).toBe(1);
    expect(coverage.pregameCovered).toBe(0);
    expect(coverage.coveragePercent).toBe(0);
  });

  it("counts a DK game with no research match as NOT_MATCHED", () => {
    const mr = matchReport({ "ZZZ@YYY 07:05PM ET": { status: "unmatched", research_game_id: null, dk_away: "ZZZ", dk_home: "YYY" } });
    const coverage = buildDkSlateVegasCoverage(mr, report([]));
    expect(coverage.notMatched).toBe(1);
    expect(coverage.games[0].vegasStatus).toBe("NOT_MATCHED");
  });

  it("counts a matched game with no environment report entry as MISSING", () => {
    const mr = matchReport({ a: { status: "matched", research_game_id: "g-not-in-report", dk_away: "CLE", dk_home: "DET" } });
    const coverage = buildDkSlateVegasCoverage(mr, report([]));
    expect(coverage.missing).toBe(1);
  });

  it("counts a matched game whose vegas field is null as MISSING", () => {
    const noVegas = buildGameEnvironmentReport({ game_id: "g1", vegas: null });
    const mr = matchReport({ a: { status: "matched", research_game_id: "g1", dk_away: "CLE", dk_home: "DET" } });
    const coverage = buildDkSlateVegasCoverage(mr, report([noVegas]));
    expect(coverage.missing).toBe(1);
  });

  it("counts INVALID vegas separately from MISSING", () => {
    const invalid = buildGameEnvironmentReport({
      game_id: "g1",
      vegas: { ...buildGameEnvironmentReport().vegas!, vegas_projection_status: "INVALID", implied_runs_is_valid: false, home_implied_runs: null, away_implied_runs: null },
    });
    const mr = matchReport({ a: { status: "matched", research_game_id: "g1", dk_away: "CLE", dk_home: "DET" } });
    const coverage = buildDkSlateVegasCoverage(mr, report([invalid]));
    expect(coverage.invalid).toBe(1);
    expect(coverage.missing).toBe(0);
  });

  it("only reports lastPregameUpdate for LIVE_PREGAME/PREGAME_FROZEN, never IN_PLAY_ONLY/MISSING", () => {
    const inPlay = buildGameEnvironmentReport({
      game_id: "g1",
      vegas: { ...buildGameEnvironmentReport().vegas!, vegas_projection_status: "IN_PLAY_ONLY", retrieved_at: "2026-08-17T23:00:00Z" },
    });
    const mr = matchReport({ a: { status: "matched", research_game_id: "g1", dk_away: "CLE", dk_home: "DET" } });
    const coverage = buildDkSlateVegasCoverage(mr, report([inPlay]));
    expect(coverage.games[0].lastPregameUpdate).toBeNull();
  });

  it("computes a partial coverage percentage rounded to one decimal", () => {
    const covered = buildGameEnvironmentReport({ game_id: "g1", vegas: { ...buildGameEnvironmentReport().vegas!, vegas_projection_status: "LIVE_PREGAME" } });
    const missing = buildGameEnvironmentReport({ game_id: "g2", vegas: null });
    const missing2 = buildGameEnvironmentReport({ game_id: "g3", vegas: null });
    const env = report([covered, missing, missing2]);
    const mr = matchReport({
      a: { status: "matched", research_game_id: "g1", dk_away: "CLE", dk_home: "DET" },
      b: { status: "matched", research_game_id: "g2", dk_away: "BOS", dk_home: "NYY" },
      c: { status: "matched", research_game_id: "g3", dk_away: "SEA", dk_home: "OAK" },
    });
    const coverage = buildDkSlateVegasCoverage(mr, env);
    expect(coverage.coveragePercent).toBeCloseTo(33.3, 1);
  });
});
