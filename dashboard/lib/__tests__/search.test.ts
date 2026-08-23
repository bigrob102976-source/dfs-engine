import { describe, expect, it } from "vitest";

import { buildSearchIndex, filterSearchIndex } from "../search";
import type { LineupSet, PitcherEvaluation, PlayerRow } from "../types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1001",
    playerType: "pitcher",
    name: "Dylan Cease",
    team: "TOR",
    opponent: "BOS",
    gameId: "g1",
    position: "P",
    positions: ["P"],
    battingOrder: null,
    salary: 9500,
    projection: 20.0,
    ceiling: 30.0,
    floor: 12.0,
    overall: 75.0,
    power: null,
    matchup: null,
    risk: 30.0,
    confidence: 90.0,
    ownership: null,
    ownershipTier: null,
    chalkScore: null,
    leverage: null,
    tags: [],
    reasons: [],
    lineupStatus: null, matchStatus: null, eligibilityStatus: null, optimizerEligible: false,
    mlProjection: null, mlProjectionStatus: null,
    blueCollarProjection: null, blueCollarMatchStatus: null,
    raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

describe("buildSearchIndex", () => {
  it("marks ownership presence based on the joined row", () => {
    const withOwnership = row({ ownership: 42.0 });
    const withoutOwnership = row({ id: "1002", name: "Other Player", ownership: null });
    const index = buildSearchIndex({ pitcherRows: [withOwnership, withoutOwnership], hitterRows: [], lineupSet: null, pitcherEvaluation: null });
    expect(index.find((e) => e.id === "1001")!.inOwnership).toBe(true);
    expect(index.find((e) => e.id === "1002")!.inOwnership).toBe(false);
  });

  it("counts optimizer lineup usage by mlb_player_id", () => {
    const lineupSet = {
      lineups: [
        { assignments: [{ mlb_player_id: "1001", dk_player_id: "d1" }] },
        { assignments: [{ mlb_player_id: "1001", dk_player_id: "d1" }] },
        { assignments: [{ mlb_player_id: "2002", dk_player_id: "d2" }] },
      ],
    } as unknown as LineupSet;
    const index = buildSearchIndex({ pitcherRows: [row()], hitterRows: [], lineupSet, pitcherEvaluation: null });
    expect(index[0].optimizerLineupCount).toBe(2);
  });

  it("marks yesterday-evaluation presence when the player_id was graded", () => {
    const evaluation = { records: [{ player_id: "1001" }] } as unknown as PitcherEvaluation;
    const index = buildSearchIndex({ pitcherRows: [row()], hitterRows: [], lineupSet: null, pitcherEvaluation: evaluation });
    expect(index[0].inYesterdayEvaluation).toBe(true);
  });
});

describe("filterSearchIndex", () => {
  const index = buildSearchIndex({
    pitcherRows: [row({ name: "Dylan Cease", team: "TOR" }), row({ id: "2", name: "Paul Skenes", team: "PIT" })],
    hitterRows: [],
    lineupSet: null,
    pitcherEvaluation: null,
  });

  it("matches by partial, case-insensitive name", () => {
    expect(filterSearchIndex(index, "cease")).toHaveLength(1);
    expect(filterSearchIndex(index, "CEASE")[0].name).toBe("Dylan Cease");
  });

  it("matches by team", () => {
    expect(filterSearchIndex(index, "PIT")).toHaveLength(1);
  });

  it("returns nothing for an empty query", () => {
    expect(filterSearchIndex(index, "")).toEqual([]);
    expect(filterSearchIndex(index, "   ")).toEqual([]);
  });

  it("returns nothing when there is no match", () => {
    expect(filterSearchIndex(index, "zzz-nobody")).toEqual([]);
  });
});
