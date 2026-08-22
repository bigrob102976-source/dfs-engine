import { describe, expect, it } from "vitest";

import {
  filterHitterRowsByEligibility,
  filterPitcherRowsByEligibility,
  HITTER_ELIGIBILITY_OPTIONS,
  isHitterEligibilityFilter,
  isPitcherEligibilityFilter,
  PITCHER_ELIGIBILITY_OPTIONS,
} from "../eligibilityFilter";
import type { PlayerRow } from "../types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1", playerType: "pitcher", name: "Player", team: "BOS", opponent: "TOR", gameId: "g1",
    position: "P", positions: ["P"], battingOrder: null, salary: 8000, projection: 20, ceiling: 32, floor: 8,
    overall: null, power: null, matchup: null, risk: null, confidence: null, ownership: null, ownershipTier: null,
    chalkScore: null, leverage: null, tags: [], reasons: [], lineupStatus: null, matchStatus: "matched",
    eligibilityStatus: null, optimizerEligible: false, mlProjection: null, mlProjectionStatus: null, raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

describe("isPitcherEligibilityFilter / isHitterEligibilityFilter", () => {
  it("accepts every listed option value and rejects anything else", () => {
    for (const o of PITCHER_ELIGIBILITY_OPTIONS) expect(isPitcherEligibilityFilter(o.value)).toBe(true);
    expect(isPitcherEligibilityFilter("bogus")).toBe(false);
    expect(isPitcherEligibilityFilter(undefined)).toBe(false);

    for (const o of HITTER_ELIGIBILITY_OPTIONS) expect(isHitterEligibilityFilter(o.value)).toBe(true);
    expect(isHitterEligibilityFilter("bogus")).toBe(false);
  });
});

describe("filterPitcherRowsByEligibility", () => {
  const starter = row({ id: "sp", eligibilityStatus: "STARTING_PITCHER", optimizerEligible: true });
  const relief = row({ id: "rp", eligibilityStatus: "RELIEF_PITCHER", optimizerEligible: false });
  const unmatched = row({ id: "u", eligibilityStatus: "UNMATCHED", optimizerEligible: false });
  const ambiguous = row({ id: "a", eligibilityStatus: "AMBIGUOUS", optimizerEligible: false });
  // A research-board-only row with no matching DK pool at all -- null
  // status. Since research pitchers.json only ever contains probable
  // starters, this must be treated as starting-equivalent.
  const noPoolMatch = row({ id: "np", eligibilityStatus: null, optimizerEligible: false });
  const rows = [starter, relief, unmatched, ambiguous, noPoolMatch];

  it("'starting' includes STARTING_PITCHER and null (research-board-only) rows, excludes relief/unmatched/ambiguous", () => {
    const result = filterPitcherRowsByEligibility(rows, "starting");
    expect(result.map((r) => r.id).sort()).toEqual(["np", "sp"]);
  });

  it("'relief' includes only RELIEF_PITCHER", () => {
    expect(filterPitcherRowsByEligibility(rows, "relief").map((r) => r.id)).toEqual(["rp"]);
  });

  it("'unmatched' includes UNMATCHED and AMBIGUOUS", () => {
    expect(filterPitcherRowsByEligibility(rows, "unmatched").map((r) => r.id).sort()).toEqual(["a", "u"]);
  });

  it("'all' returns every row unfiltered", () => {
    expect(filterPitcherRowsByEligibility(rows, "all")).toHaveLength(5);
  });
});

describe("filterHitterRowsByEligibility", () => {
  const confirmed = row({ id: "sh", playerType: "hitter", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true });
  const bench = row({ id: "b", playerType: "hitter", eligibilityStatus: "BENCH", optimizerEligible: false });
  const unconfirmed = row({ id: "lu", playerType: "hitter", eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false });
  const noPoolMatch = row({ id: "np", playerType: "hitter", eligibilityStatus: null, optimizerEligible: false });
  const rows = [confirmed, bench, unconfirmed, noPoolMatch];

  it("'confirmed' includes STARTING_HITTER and null (research-board-only) rows, excludes bench/unconfirmed", () => {
    expect(filterHitterRowsByEligibility(rows, "confirmed").map((r) => r.id).sort()).toEqual(["np", "sh"]);
  });

  it("'bench' includes only BENCH", () => {
    expect(filterHitterRowsByEligibility(rows, "bench").map((r) => r.id)).toEqual(["b"]);
  });

  it("'unconfirmed' includes only LINEUP_UNCONFIRMED", () => {
    expect(filterHitterRowsByEligibility(rows, "unconfirmed").map((r) => r.id)).toEqual(["lu"]);
  });

  it("'all' returns every row unfiltered", () => {
    expect(filterHitterRowsByEligibility(rows, "all")).toHaveLength(4);
  });
});
