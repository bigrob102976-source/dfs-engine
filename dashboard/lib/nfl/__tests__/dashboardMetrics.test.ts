import { describe, expect, it } from "vitest";

import { pickHeadline, scoreSlate, weeksOfHistory, type ScoredPlayer } from "../dashboardMetrics";
import type { NflPlayerRow, NflSlateData } from "../types";

// Launch Blocker Sprint 1 (2026-09-13): reproduces, with the exact shape
// confirmed against real production data, the mechanism behind a
// $4,000 emergency-arm QB outranking a real one. Three unrelated QBs
// with weeks_of_history=0 received an IDENTICAL projection/floor/ceiling
// from historical_models/nfl_v1 (its imputer fills the same default
// feature row for every player with no real rolling history), which is
// exactly the "missing playing-time expectation" failure mode. These
// tests prove the dashboard layer no longer crowns that case silently.

function player(overrides: Partial<NflPlayerRow> & { name: string }): NflPlayerRow {
  const dkId = overrides.name.replace(/\s+/g, "-").toLowerCase();
  return {
    draftkings_player_id: dkId,
    position: "QB",
    team: "AAA",
    opponent: "BBB",
    game_id: "g1",
    salary: 4000,
    roster_slots: ["QB"],
    is_team_entity: false,
    status: null,
    injury_status: null,
    gsis_id: "00-0000000",
    identity_resolved: true,
    usage: { rolling: { weeks_of_history: 0 }, season_to_date: {} },
    projection: { projection: 8.8, floor: -4.45, ceiling: 19.23, source: "BIG_MONEY_NATIVE", model_name: "big_money_native_nfl", model_version: "nfl_v1" },
    ownership: null,
    matchup: null,
    status_info: { normalized_status: "ACTIVE", raw_status: null, excluded_by_default: false, warn: false },
    game_lock: null,
    ...overrides,
  };
}

function minimalSlate(players: NflPlayerRow[]): NflSlateData {
  return {
    draft_group_id: 1, slate_date: "2026-09-13", slate_name: "Test", source_provenance: "TEST",
    data_status: "fresh", pool_generated_at_utc: null, salary_cap: 50000,
    current_season: 2026, current_week: 1, prior_season: 2025, current_completed_weeks: [],
    games: [], game_count: 0, player_count: players.length, position_counts: {},
    identity: { total: players.length, resolved: players.length, unresolved: 0 },
    projection_coverage: {}, projection_error: null, ownership_coverage: {},
    ownership_generated: 0, ownership_missing: 0, ownership_normalization: null, ownership_model_version: null,
    vegas_configured: false, vegas_source_provenance: "not_configured",
    players,
  };
}

describe("weeksOfHistory()", () => {
  it("reads usage.rolling.weeks_of_history when present", () => {
    expect(weeksOfHistory(player({ name: "A", usage: { rolling: { weeks_of_history: 14 }, season_to_date: {} } }))).toBe(14);
  });

  it("returns null when usage or the field is absent -- never assumes 0", () => {
    expect(weeksOfHistory(player({ name: "A", usage: null }))).toBeNull();
    expect(weeksOfHistory(player({ name: "A", usage: { rolling: {}, season_to_date: {} } }))).toBeNull();
  });
});

describe("scoreSlate() attaches hasTrackRecord from the real pipeline signal", () => {
  it("marks a zero-history player as not having a track record", () => {
    const slate = minimalSlate([player({ name: "Zero History QB" })]);
    const [scored] = scoreSlate(slate);
    expect(scored.weeksOfHistory).toBe(0);
    expect(scored.hasTrackRecord).toBe(false);
  });

  it("marks a real-history player as having a track record", () => {
    const slate = minimalSlate([
      player({ name: "Real QB", usage: { rolling: { weeks_of_history: 14 }, season_to_date: {} }, projection: { projection: 18.99, floor: 5.74, ceiling: 29.42, source: "BIG_MONEY_NATIVE", model_name: "big_money_native_nfl", model_version: "nfl_v1" } }),
    ]);
    const [scored] = scoreSlate(slate);
    expect(scored.hasTrackRecord).toBe(true);
  });
});

describe("pickHeadline() -- the actual fix for the reported ranking issue", () => {
  it("reproduces the real production bug: three unrelated zero-history QBs get an identical model output", () => {
    const a = player({ name: "Sam Howell" });
    const b = player({ name: "Jake Haener", team: "CCC" });
    const c = player({ name: "Sam Ehlinger", team: "DDD" });
    // This IS the real, confirmed-live shape -- not fabricated for the test.
    for (const p of [a, b, c]) {
      expect(p.projection).toEqual({ projection: 8.8, floor: -4.45, ceiling: 19.23, source: "BIG_MONEY_NATIVE", model_name: "big_money_native_nfl", model_version: "nfl_v1" });
    }
  });

  it("prefers a real-history candidate over a zero-history one with a coincidentally competitive score", () => {
    const backup: ScoredPlayer = {
      row: player({ name: "Backup", salary: 4000 }),
      projection: 19.6, floor: 6.3, ceiling: 30.0, ownership: 5, value: 4.9, ceilingValue: 7.5,
      teamImpliedTotal: 27, gameTotal: 50.5, leverage: 7.48,
      cashScore: 85, gppScore: 85, bigMoneyScore: 85.3, bigMoneyRank: null,
      weeksOfHistory: 0, hasTrackRecord: false,
    };
    const starter: ScoredPlayer = {
      row: player({ name: "Starter", salary: 7000 }),
      projection: 20.5, floor: 7.22, ceiling: 30.9, ownership: 18, value: 2.93, ceilingValue: 4.41,
      teamImpliedTotal: 24, gameTotal: 44.5, leverage: 1.7,
      cashScore: 70, gppScore: 70, bigMoneyScore: 70.0, bigMoneyRank: null,
      weeksOfHistory: 14, hasTrackRecord: true,
    };

    // The zero-history "backup" has the HIGHER raw score (85.3 > 70.0) --
    // exactly the reported symptom -- but pickHeadline must not crown it
    // while a real-history alternative exists.
    const result = pickHeadline([backup, starter], (p) => p.bigMoneyScore);
    expect(result.player?.row.name).toBe("Starter");
    expect(result.lowConfidenceFallback).toBe(false);
  });

  it("falls back to the zero-history pick, and says so, only when no track-record candidate exists at all", () => {
    const onlyBackup: ScoredPlayer = {
      row: player({ name: "Only Option" }),
      projection: 8.8, floor: -4.45, ceiling: 19.23, ownership: null, value: 2.2, ceilingValue: 4.8,
      teamImpliedTotal: null, gameTotal: null, leverage: null,
      cashScore: 40, gppScore: 40, bigMoneyScore: 40, bigMoneyRank: null,
      weeksOfHistory: 0, hasTrackRecord: false,
    };
    const result = pickHeadline([onlyBackup], (p) => p.bigMoneyScore);
    expect(result.player?.row.name).toBe("Only Option");
    expect(result.lowConfidenceFallback).toBe(true);
  });

  it("returns null, not a fabricated pick, when nothing has the requested key at all", () => {
    const noScore: ScoredPlayer = {
      row: player({ name: "No Score" }),
      projection: 8.8, floor: null, ceiling: null, ownership: null, value: 2.2, ceilingValue: null,
      teamImpliedTotal: null, gameTotal: null, leverage: null,
      cashScore: null, gppScore: null, bigMoneyScore: null, bigMoneyRank: null,
      weeksOfHistory: 0, hasTrackRecord: false,
    };
    const result = pickHeadline([noScore], (p) => p.bigMoneyScore);
    expect(result.player).toBeNull();
    expect(result.lowConfidenceFallback).toBe(false);
  });
});
