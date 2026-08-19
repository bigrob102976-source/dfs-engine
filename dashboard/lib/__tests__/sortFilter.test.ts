import { describe, expect, it } from "vitest";

import { distinctValues, filterPlayerRows, sortRows } from "../sortFilter";
import type { PlayerRow } from "../types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1",
    playerType: "hitter",
    name: "Player",
    team: "AAA",
    opponent: "BBB",
    gameId: "g1",
    position: "OF",
    positions: ["OF"],
    battingOrder: 3,
    salary: 4000,
    projection: 8.0,
    ceiling: 15.0,
    floor: 4.0,
    overall: 60.0,
    power: 55.0,
    matchup: 50.0,
    risk: 30.0,
    confidence: 90.0,
    ownership: 20.0,
    ownershipTier: "medium",
    chalkScore: 50.0,
    leverage: 5.0,
    tags: [],
    reasons: [],
    lineupStatus: null, matchStatus: null, eligibilityStatus: null, optimizerEligible: false,
    raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

describe("sortRows", () => {
  it("sorts ascending and descending by a numeric key", () => {
    const rows = [row({ id: "a", projection: 5 }), row({ id: "b", projection: 15 }), row({ id: "c", projection: 10 })];
    expect(sortRows(rows, "projection", "asc").map((r) => r.id)).toEqual(["a", "c", "b"]);
    expect(sortRows(rows, "projection", "desc").map((r) => r.id)).toEqual(["b", "c", "a"]);
  });

  it("sorts strings alphabetically", () => {
    const rows = [row({ id: "a", name: "Zeta" }), row({ id: "b", name: "Alpha" })];
    expect(sortRows(rows, "name", "asc").map((r) => r.id)).toEqual(["b", "a"]);
  });

  it("always sorts nulls to the end regardless of direction", () => {
    const rows = [row({ id: "a", ownership: 10 }), row({ id: "b", ownership: null }), row({ id: "c", ownership: 5 })];
    expect(sortRows(rows, "ownership", "asc").map((r) => r.id)).toEqual(["c", "a", "b"]);
    expect(sortRows(rows, "ownership", "desc").map((r) => r.id)).toEqual(["a", "c", "b"]);
  });

  it("does not mutate the input array", () => {
    const rows = [row({ id: "a", projection: 5 }), row({ id: "b", projection: 15 })];
    const original = [...rows];
    sortRows(rows, "projection", "desc");
    expect(rows).toEqual(original);
  });
});

describe("filterPlayerRows", () => {
  const rows = [
    row({ id: "1", team: "PHI", position: "OF", ownershipTier: "high", confidence: 95, risk: 20, tags: ["chalk"], salary: 5000 }),
    row({ id: "2", team: "NYY", position: "1B", positions: ["1B"], ownershipTier: "low", confidence: 60, risk: 60, tags: ["contrarian"], salary: 2500 }),
  ];

  it("filters by team", () => {
    expect(filterPlayerRows(rows, { team: "PHI" }).map((r) => r.id)).toEqual(["1"]);
  });

  it("filters by position (checks eligibility list, not just primary)", () => {
    const multi = row({ id: "3", position: "1B", positions: ["1B", "OF"] });
    expect(filterPlayerRows([...rows, multi], { position: "OF" }).map((r) => r.id)).toEqual(["1", "3"]);
  });

  it("filters by ownership tier", () => {
    expect(filterPlayerRows(rows, { ownershipTier: "low" }).map((r) => r.id)).toEqual(["2"]);
  });

  it("filters by minimum confidence", () => {
    expect(filterPlayerRows(rows, { minConfidence: 90 }).map((r) => r.id)).toEqual(["1"]);
  });

  it("filters by maximum risk", () => {
    expect(filterPlayerRows(rows, { maxRisk: 30 }).map((r) => r.id)).toEqual(["1"]);
  });

  it("filters by tag", () => {
    expect(filterPlayerRows(rows, { tag: "contrarian" }).map((r) => r.id)).toEqual(["2"]);
  });

  it("filters by salary range", () => {
    expect(filterPlayerRows(rows, { minSalary: 3000, maxSalary: 6000 }).map((r) => r.id)).toEqual(["1"]);
  });

  it("filters by search text against player name", () => {
    const named = [row({ id: "1", name: "Aaron Judge" }), row({ id: "2", name: "Kyle Schwarber" })];
    expect(filterPlayerRows(named, { search: "judge" }).map((r) => r.id)).toEqual(["1"]);
  });

  it("combines multiple filters with AND semantics", () => {
    expect(filterPlayerRows(rows, { team: "PHI", ownershipTier: "high" }).map((r) => r.id)).toEqual(["1"]);
    expect(filterPlayerRows(rows, { team: "PHI", ownershipTier: "low" })).toEqual([]);
  });

  it("returns all rows when no filters are supplied", () => {
    expect(filterPlayerRows(rows, {})).toHaveLength(2);
  });
});

describe("distinctValues", () => {
  it("returns unique, sorted, non-empty values", () => {
    const rows = [row({ team: "PHI" }), row({ team: "NYY" }), row({ team: "PHI" })];
    expect(distinctValues(rows, (r) => r.team)).toEqual(["NYY", "PHI"]);
  });

  it("ignores null/undefined values", () => {
    const rows = [row({ ownershipTier: "high" }), row({ ownershipTier: null })];
    expect(distinctValues(rows, (r) => r.ownershipTier)).toEqual(["high"]);
  });
});
