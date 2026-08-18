import { describe, expect, it } from "vitest";

import { buildProjectionLabRows, buildProjectionLabSummary } from "../projectionLab";
import type { PlayerRow } from "../types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "p1", playerType: "hitter", name: "Test Player", team: "NYY", opponent: "BOS", gameId: "g1",
    position: "OF", positions: ["OF"], battingOrder: 3, salary: 5000, projection: 10, ceiling: 15, floor: 5,
    overall: null, power: null, matchup: null, risk: null, confidence: null, ownership: 20, ownershipTier: null,
    chalkScore: null, leverage: 3, tags: [], reasons: [], lineupStatus: null, matchStatus: null, raw: {} as PlayerRow["raw"],
    ...overrides,
  };
}

describe("buildProjectionLabRows", () => {
  it("joins BlueCollar/Native/AI onto each row by id, honestly leaving unloaded sources null", () => {
    const rows = [row({ id: "p1" }), row({ id: "p2", name: "No Data Player" })];
    const externalByPlayerId = new Map([["p1", { independentProjection: 10, externalProjection: 9.5, adjustedProjection: 10.2, adjustmentDelta: 0.2, adjustmentPercent: 2, adjustmentReasons: [] }]]);
    const nativeByPlayerId = new Map([["p1", { native_projection: 11 } as never]]);
    const aiByPlayerId = new Map([["p1", { ai_projection: 12, ai_confidence: 80, total_adjustment: 1 } as never]]);
    const actualByPlayerId = new Map([["p1", 14.5]]);

    const result = buildProjectionLabRows(rows, externalByPlayerId, nativeByPlayerId, aiByPlayerId, actualByPlayerId);

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
  });

  it("falls back to Native for the Big Money side of the BlueCollar delta when AI is unavailable", () => {
    const rows = [row({ id: "p1" })];
    const externalByPlayerId = new Map([["p1", { independentProjection: 10, externalProjection: 8, adjustedProjection: null, adjustmentDelta: null, adjustmentPercent: null, adjustmentReasons: [] }]]);
    const nativeByPlayerId = new Map([["p1", { native_projection: 10.5 } as never]]);
    const result = buildProjectionLabRows(rows, externalByPlayerId, nativeByPlayerId, new Map(), new Map());
    expect(result[0].bigMoneyVsBlueCollarDelta).toBe(2.5); // 10.5 - 8
  });
});

describe("buildProjectionLabSummary", () => {
  it("computes coverage counts and largest deltas without recomputing any projection", () => {
    const rows = [
      { id: "p1", name: "Judge", team: "NYY", opponent: null, gameId: null, playerType: "hitter" as const, position: "OF", salary: 6000, ownership: 20, leverage: 2, blueCollarProjection: 11.8, nativeProjection: 12.1, nativeConfidence: 80, aiProjection: 12.7, aiConfidence: 82, aiVsNativeDelta: 0.6, bigMoneyVsBlueCollarDelta: 0.9, actualDkPoints: null },
      { id: "p2", name: "Soto", team: "NYY", opponent: null, gameId: null, playerType: "hitter" as const, position: "OF", salary: 5800, ownership: 15, leverage: 1, blueCollarProjection: null, nativeProjection: 10.5, nativeConfidence: 70, aiProjection: 9.3, aiConfidence: 75, aiVsNativeDelta: -1.2, bigMoneyVsBlueCollarDelta: null, actualDkPoints: null },
    ];
    const summary = buildProjectionLabSummary(rows);
    expect(summary.players).toBe(2);
    expect(summary.blueCollarCoverage).toBe(1);
    expect(summary.nativeCoverage).toBe(2);
    expect(summary.aiCoverage).toBe(2);
    expect(summary.largestAiUpgrade?.id).toBe("p1");
    expect(summary.largestAiDowngrade?.id).toBe("p2");
    expect(summary.largestBigMoneyVsBlueCollarDifference?.id).toBe("p1");
  });
});
