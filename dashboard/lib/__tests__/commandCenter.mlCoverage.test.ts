import { describe, expect, it } from "vitest";

import { buildMlCoverageSummary } from "../commandCenter";
import type { PlayerRow } from "../types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1", playerType: "hitter", name: "Player", team: "AAA", opponent: "BBB", gameId: "g1",
    position: "OF", positions: ["OF"], battingOrder: 1, salary: 4000, projection: 8, ceiling: 15, floor: 4,
    overall: 60, power: 55, matchup: 50, risk: 30, confidence: 90, ownership: 20, ownershipTier: "medium",
    chalkScore: 50, leverage: 5, tags: [], reasons: [], lineupStatus: "active", matchStatus: "matched",
    eligibilityStatus: "STARTING_HITTER", optimizerEligible: true, mlProjection: null, mlProjectionStatus: null,
    blueCollarProjection: null, blueCollarMatchStatus: null,
    raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

describe("buildMlCoverageSummary", () => {
  it("counts pitchers and hitters independently, never mixing the two buckets", () => {
    const rows = [
      row({ id: "p1", playerType: "pitcher", optimizerEligible: true }),
      row({ id: "p2", playerType: "pitcher", optimizerEligible: true }),
      row({ id: "h1", playerType: "hitter", optimizerEligible: true }),
      row({ id: "h2", playerType: "hitter", optimizerEligible: true }),
      row({ id: "h3", playerType: "hitter", optimizerEligible: true }),
    ];
    const mlByPlayerId = new Map([
      ["p1", { projection_status: "LIVE_PREGAME" }],
      ["h1", { projection_status: "LIVE_PREGAME" }],
      ["h2", { projection_status: "PREGAME_FROZEN" }],
    ]);
    const summary = buildMlCoverageSummary(rows, mlByPlayerId);
    expect(summary.eligiblePitchers).toBe(2);
    expect(summary.projectedPitchers).toBe(1);
    expect(summary.eligibleHitters).toBe(3);
    expect(summary.projectedHitters).toBe(2);
  });

  it("excludes players that are not optimizer-eligible from either bucket", () => {
    const rows = [row({ id: "bench1", playerType: "hitter", optimizerEligible: false })];
    const mlByPlayerId = new Map([["bench1", { projection_status: "LIVE_PREGAME" }]]);
    const summary = buildMlCoverageSummary(rows, mlByPlayerId);
    expect(summary.eligibleHitters).toBe(0);
    expect(summary.projectedHitters).toBe(0);
  });

  it("a MISSING or INVALID_FEATURE_PARITY status never counts as projected", () => {
    const rows = [row({ id: "h1", playerType: "hitter", optimizerEligible: true })];
    const mlByPlayerId = new Map([["h1", { projection_status: "MISSING" }]]);
    const summary = buildMlCoverageSummary(rows, mlByPlayerId);
    expect(summary.eligibleHitters).toBe(1);
    expect(summary.projectedHitters).toBe(0);
  });

  it("returns all zeros for an empty row set", () => {
    const summary = buildMlCoverageSummary([], new Map());
    expect(summary).toEqual({ eligiblePitchers: 0, projectedPitchers: 0, eligibleHitters: 0, projectedHitters: 0 });
  });
});
