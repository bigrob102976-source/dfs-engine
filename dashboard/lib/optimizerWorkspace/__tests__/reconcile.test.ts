import { describe, expect, it } from "vitest";

import { reconcileConstraintsWithPool } from "../reconcile";
import type { OptimizerPoolResult, PoolPlayerRow } from "../types";

function player(overrides: Partial<PoolPlayerRow> = {}): PoolPlayerRow {
  return {
    dkPlayerId: "d1",
    mlbPlayerId: "h1",
    name: "Leadoff Hitter",
    team: "BOS",
    opponent: "TOR",
    gameId: "g1",
    playerType: "hitter",
    positions: ["OF"],
    battingOrder: 1,
    salary: 4000,
    projection: 10,
    ceiling: 18,
    value: 2.5,
    ownership: null,
    leverage: null,
    risk: 30,
    confidence: 80,
    lineupStatus: "active",
    matchStatus: "matched",
    externalProjection: null,
    adjustedProjection: null,
    adjustmentDelta: null,
    adjustmentPercent: null,
    adjustmentReasons: [],
    aiProjection: null,
    aiCeiling: null,
    aiFloor: null,
    aiDelta: null,
    aiConfidence: null,
    aiRisk: null,
    aiGrade: null,
    aiValueScore: null,
    aiSignals: [],
    aiReasons: [],
    aiSummary: null,
    nativeProjection: null,
    nativeCeiling: null,
    nativeFloor: null,
    nativeDelta: null,
    nativeConfidence: null,
    nativeReasons: [],
    nativeExpectedPa: null,
    nativeExpectedInnings: null,
    nativeHitterComponents: null,
    nativePitcherComponents: null,
    ...overrides,
  };
}

function pool(players: PoolPlayerRow[]): OptimizerPoolResult {
  return {
    date: "2026-08-12",
    slateId: "mock-main",
    slateName: "Mock Main (Dev)",
    providerName: "mock_dev_provider",
    isMock: true,
    providerSource: "mock_explicit",
    generatedAt: "2026-08-12T18:00:00Z",
    players,
    activePlayers: players.filter((p) => p.lineupStatus === "active").length,
    pitcherCount: 0,
    hitterCount: 0,
    hasExternalProjections: false,
    hasAiProjections: false,
    hasNativeProjections: false,
    confirmedLineupGames: 0,
    unconfirmedLineupGames: 0,
    unmatchedCount: 0,
    slateGames: 1,
    rosterFeasibilityPass: true,
    salaryCap: 50000,
    hasOwnership: false,
    vegasCoverage: { dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 0, games: [] },
  };
}

describe("reconcileConstraintsWithPool", () => {
  it("keeps a lock/exclusion/exposure for a player who is still active", () => {
    const result = reconcileConstraintsWithPool(pool([player({ dkPlayerId: "d1" })]), {
      locks: ["d1"],
      exclusions: [],
      maxExposure: { d1: 0.5 },
    });
    expect(result.state.locks).toEqual(["d1"]);
    expect(result.state.maxExposure).toEqual({ d1: 0.5 });
    expect(result.warnings).toEqual([]);
  });

  it("silently drops a lock/exclusion/exposure for a player not on this slate at all", () => {
    const result = reconcileConstraintsWithPool(pool([player({ dkPlayerId: "d1" })]), {
      locks: ["not-on-this-slate"],
      exclusions: ["also-not-here"],
      maxExposure: { "still-not-here": 0.25 },
    });
    expect(result.state).toEqual({ locks: [], exclusions: [], maxExposure: {} });
    expect(result.warnings).toEqual([]);
  });

  it("drops a lock with a warning when the player is present but scratched", () => {
    const result = reconcileConstraintsWithPool(pool([player({ dkPlayerId: "d1", name: "Scratched Guy", lineupStatus: "lineup_not_confirmed" })]), {
      locks: ["d1"],
      exclusions: [],
      maxExposure: {},
    });
    expect(result.state.locks).toEqual([]);
    expect(result.warnings).toEqual(["Locked player Scratched Guy is no longer active."]);
  });

  it("keeps an exclusion for a scratched player without warning (excluding an inactive player is harmless)", () => {
    const result = reconcileConstraintsWithPool(pool([player({ dkPlayerId: "d1", lineupStatus: "lineup_not_confirmed" })]), {
      locks: [],
      exclusions: ["d1"],
      maxExposure: {},
    });
    expect(result.state.exclusions).toEqual(["d1"]);
    expect(result.warnings).toEqual([]);
  });
});
