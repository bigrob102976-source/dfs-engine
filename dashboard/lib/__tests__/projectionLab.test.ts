import { describe, expect, it } from "vitest";

import { buildProjectionLabRows, buildProjectionLabSummary } from "../projectionLab";
import type { PlayerRow } from "../types";

function bcPlayer(overrides: Record<string, unknown> = {}) {
  return {
    bluecollar_local_id: "test|nyy|of", name: "Test Player", team: "NYY", position: "OF", opponent: "BOS",
    salary: 5000, raw_projection: 9.5, usable_projection: 9.5, match_status: "matched" as const,
    match_confidence: "name_team_exact", mlb_player_id: "p1", candidate_mlb_ids: [], candidate_names: [],
    ...overrides,
  };
}

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "p1", playerType: "hitter", name: "Test Player", team: "NYY", opponent: "BOS", gameId: "g1",
    position: "OF", positions: ["OF"], battingOrder: 3, salary: 5000, projection: 10, ceiling: 15, floor: 5,
    overall: null, power: null, matchup: null, risk: null, confidence: null, ownership: 20, ownershipTier: null,
    chalkScore: null, leverage: 3, tags: [], reasons: [], lineupStatus: null, matchStatus: null,
    eligibilityStatus: "STARTING_HITTER", optimizerEligible: true, mlProjection: null, mlProjectionStatus: null,
    blueCollarProjection: null, blueCollarMatchStatus: null, raw: {} as PlayerRow["raw"],
    ...overrides,
  };
}

describe("buildProjectionLabRows", () => {
  it("joins BlueCollar/Native/AI onto each row by id, honestly leaving unloaded sources null", () => {
    const rows = [row({ id: "p1" }), row({ id: "p2", name: "No Data Player" })];
    const blueCollarByPlayerId = new Map([["p1", bcPlayer({ usable_projection: 9.5 }) as never]]);
    const nativeByPlayerId = new Map([["p1", { native_projection: 11 } as never]]);
    const aiByPlayerId = new Map([["p1", { ai_projection: 12, ai_confidence: 80, total_adjustment: 1 } as never]]);
    const actualByPlayerId = new Map([["p1", 14.5]]);

    const result = buildProjectionLabRows(rows, blueCollarByPlayerId, nativeByPlayerId, aiByPlayerId, actualByPlayerId);

    expect(result).toHaveLength(2);
    const p1 = result.find((r) => r.id === "p1")!;
    expect(p1.blueCollarProjection).toBe(9.5);
    expect(p1.nativeProjection).toBe(11);
    expect(p1.aiProjection).toBe(12);
    expect(p1.aiVsNativeDelta).toBe(1);
    expect(p1.bigMoneyVsBlueCollarDelta).toBe(2.5); // 12 - 9.5
    expect(p1.actualDkPoints).toBe(14.5);

    const p2 = result.find((r) => r.id === "p2")!;
    expect(p2.blueCollarProjection).toBeNull();
    expect(p2.nativeProjection).toBeNull();
    expect(p2.aiProjection).toBeNull();
    expect(p2.actualDkPoints).toBeNull();
    expect(p2.fantasyProsProjection).toBeNull();
    expect(p2.fantasyProsMatchStatus).toBeNull();
  });

  it("falls back to Native for the Big Money side of the BlueCollar delta when AI is unavailable", () => {
    const rows = [row({ id: "p1" })];
    const blueCollarByPlayerId = new Map([["p1", bcPlayer({ usable_projection: 8 }) as never]]);
    const nativeByPlayerId = new Map([["p1", { native_projection: 10.5 } as never]]);
    const result = buildProjectionLabRows(rows, blueCollarByPlayerId, nativeByPlayerId, new Map(), new Map());
    expect(result[0].bigMoneyVsBlueCollarDelta).toBe(2.5); // 10.5 - 8
  });

  it("joins FantasyPros (dk_points) onto the row and computes FP vs Native/AI deltas, honestly null when unmatched", () => {
    const rows = [row({ id: "p1" }), row({ id: "p2", name: "No FantasyPros Data" })];
    const nativeByPlayerId = new Map([["p1", { native_projection: 10 } as never]]);
    const aiByPlayerId = new Map([["p1", { ai_projection: 11, ai_confidence: 80, total_adjustment: 1 } as never]]);
    const fantasyProsByPlayerId = new Map([
      ["p1", { fantasypros_id: "1", name: "Test Player", team: "NYY", player_type: "hitter" as const, yahoo_id: null, raw_stats: {}, dk_points: 9.5, dk_points_breakdown: {}, match_status: "matched" as const, match_confidence: "name_team_exact", mlb_player_id: "p1", candidate_mlb_ids: [], candidate_names: [] }],
    ]);

    const result = buildProjectionLabRows(rows, new Map(), nativeByPlayerId, aiByPlayerId, new Map(), fantasyProsByPlayerId);

    const p1 = result.find((r) => r.id === "p1")!;
    expect(p1.fantasyProsProjection).toBe(9.5);
    expect(p1.fantasyProsMatchStatus).toBe("matched");
    expect(p1.fpVsNativeDelta).toBe(-0.5); // 9.5 - 10
    expect(p1.fpVsAiDelta).toBe(-1.5); // 9.5 - 11
    expect(p1.bigMoneyVsFantasyProsDelta).toBe(1.5); // 11 (AI, Big Money final) - 9.5

    const p2 = result.find((r) => r.id === "p2")!;
    expect(p2.fantasyProsProjection).toBeNull();
    expect(p2.fantasyProsMatchStatus).toBeNull();
    expect(p2.fpVsNativeDelta).toBeNull();
  });

  it("never feeds a FantasyPros value into nativeProjection/aiProjection -- they stay exactly what Native/AI's own snapshots said", () => {
    const rows = [row({ id: "p1" })];
    const nativeByPlayerId = new Map([["p1", { native_projection: 10 } as never]]);
    const fantasyProsByPlayerId = new Map([
      ["p1", { fantasypros_id: "1", name: "Test Player", team: "NYY", player_type: "hitter" as const, yahoo_id: null, raw_stats: {}, dk_points: 999, dk_points_breakdown: {}, match_status: "matched" as const, match_confidence: "name_team_exact", mlb_player_id: "p1", candidate_mlb_ids: [], candidate_names: [] }],
    ]);
    const result = buildProjectionLabRows(rows, new Map(), nativeByPlayerId, new Map(), new Map(), fantasyProsByPlayerId);
    expect(result[0].nativeProjection).toBe(10); // unaffected by FantasyPros' wildly different 999
  });
});

describe("buildProjectionLabSummary", () => {
  it("computes coverage counts and largest deltas without recomputing any projection", () => {
    const rows = [
      { id: "p1", name: "Judge", team: "NYY", opponent: null, gameId: null, playerType: "hitter" as const, position: "OF", salary: 6000, ownership: 20, leverage: 2, blueCollarProjection: 11.8, nativeProjection: 12.1, nativeConfidence: 80, aiProjection: 12.7, aiConfidence: 82, fantasyProsProjection: 10.9, fantasyProsMatchStatus: "matched" as const, mlProjection: null, mlDataQualityScore: null, mlProjectionStatus: null, aiVsNativeDelta: 0.6, bigMoneyVsBlueCollarDelta: 0.9, fpVsNativeDelta: -1.2, fpVsAiDelta: -1.8, bigMoneyVsFantasyProsDelta: 1.8, mlVsNativeDelta: null, mlVsAiDelta: null, mlVsFantasyProsDelta: null, actualDkPoints: null, eligibilityStatus: "STARTING_HITTER", optimizerEligible: true },
      { id: "p2", name: "Soto", team: "NYY", opponent: null, gameId: null, playerType: "hitter" as const, position: "OF", salary: 5800, ownership: 15, leverage: 1, blueCollarProjection: null, nativeProjection: 10.5, nativeConfidence: 70, aiProjection: 9.3, aiConfidence: 75, fantasyProsProjection: null, fantasyProsMatchStatus: null, mlProjection: null, mlDataQualityScore: null, mlProjectionStatus: null, aiVsNativeDelta: -1.2, bigMoneyVsBlueCollarDelta: null, fpVsNativeDelta: null, fpVsAiDelta: null, bigMoneyVsFantasyProsDelta: null, mlVsNativeDelta: null, mlVsAiDelta: null, mlVsFantasyProsDelta: null, actualDkPoints: null, eligibilityStatus: "STARTING_HITTER", optimizerEligible: true },
      { id: "p3", name: "Reliever", team: "BOS", opponent: null, gameId: null, playerType: "pitcher" as const, position: "P", salary: 4200, ownership: 1, leverage: 0, blueCollarProjection: null, nativeProjection: 3.0, nativeConfidence: 40, aiProjection: null, aiConfidence: null, fantasyProsProjection: 3.5, fantasyProsMatchStatus: "matched" as const, mlProjection: 4.2, mlDataQualityScore: 0.9, mlProjectionStatus: "LIVE_PREGAME" as const, aiVsNativeDelta: null, bigMoneyVsBlueCollarDelta: null, fpVsNativeDelta: 0.5, fpVsAiDelta: null, bigMoneyVsFantasyProsDelta: -0.5, mlVsNativeDelta: 1.2, mlVsAiDelta: null, mlVsFantasyProsDelta: 0.7, actualDkPoints: null, eligibilityStatus: "RELIEF_PITCHER", optimizerEligible: false },
    ];
    const summary = buildProjectionLabSummary(rows);
    expect(summary.players).toBe(3);
    expect(summary.eligiblePlayers).toBe(2);
    expect(summary.blueCollarCoverage).toBe(1);
    expect(summary.nativeCoverage).toBe(3);
    expect(summary.aiCoverage).toBe(2);
    // Native/AI eligible coverage is measured against eligiblePlayers only
    // -- the non-eligible reliever's own native projection must not
    // count toward "eligible coverage" even though it exists.
    expect(summary.nativeEligibleCoverage).toBe(2);
    expect(summary.aiEligibleCoverage).toBe(2);
    expect(summary.largestAiUpgrade?.id).toBe("p1");
    expect(summary.largestAiDowngrade?.id).toBe("p2");
    expect(summary.largestBigMoneyVsBlueCollarDifference?.id).toBe("p1");
    // FantasyPros coverage is measured against eligiblePlayers only -- the
    // non-eligible reliever's own FantasyPros match must not count, even
    // though a value exists (mirrors the native/AI eligible-coverage rule).
    expect(summary.fantasyProsCoverage).toBe(1);
    expect(summary.averageFantasyProsProjection).toBe(7.2); // (10.9 + 3.5) / 2
    expect(summary.largestBigMoneyOverFantasyPros?.id).toBe("p1"); // +1.8
    expect(summary.largestBigMoneyUnderFantasyPros?.id).toBe("p3"); // -0.5
    // Milestone 32.2B: only p3 (the non-eligible reliever) has an ML
    // value -- mlCoverage is measured against eligiblePlayers only, so
    // it must be 0 even though a value exists, mirroring the
    // native/AI/FantasyPros eligible-coverage rule above.
    expect(summary.mlCoverage).toBe(0);
    expect(summary.averageMlProjection).toBe(4.2);
  });
});
