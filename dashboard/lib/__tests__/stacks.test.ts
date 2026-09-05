import { describe, expect, it } from "vitest";

import { buildStackCandidates, buildStackSummaries, rankStackCandidatesByScore, rankStackCandidatesByValue, stackScore } from "../stacks";
import type { PlayerRow } from "../types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1",
    playerType: "hitter",
    name: "Player",
    team: "PHI",
    opponent: "STL",
    gameId: "g1",
    position: "OF",
    positions: ["OF"],
    battingOrder: 1,
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
    lineupStatus: "active", matchStatus: "matched",
    eligibilityStatus: "STARTING_HITTER", optimizerEligible: true,
    mlProjection: null, mlProjectionStatus: null,
    blueCollarProjection: null, blueCollarMatchStatus: null,
    raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

describe("buildStackSummaries", () => {
  it("groups hitters by team and averages their metrics (confirmed starters only)", () => {
    const rows = [
      row({ id: "1", team: "PHI", projection: 10, ownership: 30, power: 60, confidence: 90 }),
      row({ id: "2", team: "PHI", projection: 6, ownership: 10, power: 40, confidence: 80 }),
      row({ id: "3", team: "NYY", projection: 5, ownership: 15, power: 50, confidence: 70 }),
    ];
    const summaries = buildStackSummaries(rows, {});
    const phi = summaries.find((s) => s.team === "PHI")!;
    expect(phi.confirmedHitterCount).toBe(2);
    expect(phi.averageProjection).toBe(8);
    expect(phi.averageOwnership).toBe(20);
    expect(phi.averagePower).toBe(50);
    expect(phi.averageConfidence).toBe(85);
    expect(phi.status).toBe("CONFIRMED");
  });

  it("sorts teams by average projection descending", () => {
    const rows = [row({ id: "1", team: "LOW", projection: 3 }), row({ id: "2", team: "HIGH", projection: 12 })];
    const summaries = buildStackSummaries(rows, {});
    expect(summaries.map((s) => s.team)).toEqual(["HIGH", "LOW"]);
  });

  it("returns the top 5 projected hitters per team, sorted descending", () => {
    const rows = Array.from({ length: 7 }, (_, i) => row({ id: String(i), team: "PHI", projection: i }));
    const summaries = buildStackSummaries(rows, {});
    expect(summaries[0].top5).toHaveLength(5);
    expect(summaries[0].top5[0].id).toBe("6"); // highest projection first
    expect(summaries[0].top5[4].id).toBe("2");
  });

  it("pulls team popularity score from the ownership snapshot when available", () => {
    const rows = [row({ team: "PHI" })];
    const summaries = buildStackSummaries(rows, {
      PHI: { team: "PHI", team_popularity_score: 88, aggregate_projection: 0, top5_projection: 0, hitter_count: 0, aggregate_projected_ownership: 0 },
    });
    expect(summaries[0].teamPopularityScore).toBe(88);
  });

  it("leaves team popularity null when ownership hasn't been loaded", () => {
    const summaries = buildStackSummaries([row({ team: "PHI" })], {});
    expect(summaries[0].teamPopularityScore).toBeNull();
  });

  it("handles an empty hitter list", () => {
    expect(buildStackSummaries([], {})).toEqual([]);
  });

  // --------------------------------------------------------------------
  // Milestone 30.1 -- stacks reflect CONFIRMED starting lineups only.
  // Bench/unconfirmed hitters are preserved for visibility
  // (totalHitterCount) but never feed averages/top5/status.
  // --------------------------------------------------------------------

  it("confirmedHitterCount only counts optimizerEligible rows; totalHitterCount counts every preserved row", () => {
    const rows = [
      row({ id: "1", team: "LAD", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true, projection: 10 }),
      row({ id: "2", team: "LAD", eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false, projection: null, matchStatus: "unmatched" }),
      row({ id: "3", team: "LAD", eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false, projection: null, matchStatus: "unmatched" }),
    ];
    const summaries = buildStackSummaries(rows, {});
    const lad = summaries.find((s) => s.team === "LAD")!;
    expect(lad.confirmedHitterCount).toBe(1);
    expect(lad.totalHitterCount).toBe(3);
    expect(lad.status).toBe("CONFIRMED");
  });

  it("a team with zero confirmed hitters gets an empty top5 and WAITING_FOR_LINEUP status -- never a fabricated stack from bench/unconfirmed players", () => {
    const rows = [
      row({ id: "1", team: "LAD", name: "Shohei Ohtani", salary: 7100, projection: null, eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false, matchStatus: "unmatched" }),
      row({ id: "2", team: "LAD", name: "Freddie Freeman", salary: 6100, projection: null, eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false, matchStatus: "unmatched" }),
      row({ id: "3", team: "LAD", name: "Mookie Betts", salary: 4900, projection: null, eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false, matchStatus: "unmatched" }),
    ];
    const summaries = buildStackSummaries(rows, {});
    const lad = summaries.find((s) => s.team === "LAD")!;
    expect(lad.confirmedHitterCount).toBe(0);
    expect(lad.totalHitterCount).toBe(3);
    expect(lad.top5).toHaveLength(0);
    expect(lad.status).toBe("WAITING_FOR_LINEUP");
    expect(lad.averageProjection).toBeNull(); // never fabricated
  });

  it("bench hitters never appear in top5 even when a team has confirmed starters too", () => {
    const rows = [
      row({ id: "1", team: "LAD", name: "Starter", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true, projection: 8 }),
      row({ id: "2", team: "LAD", name: "Bench Guy", eligibilityStatus: "BENCH", optimizerEligible: false, projection: 20, salary: 9000 }),
    ];
    const summaries = buildStackSummaries(rows, {});
    const lad = summaries.find((s) => s.team === "LAD")!;
    expect(lad.top5.map((h) => h.name)).toEqual(["Starter"]);
    expect(lad.confirmedHitterCount).toBe(1);
    expect(lad.totalHitterCount).toBe(2);
  });

  it("ranks by projection first, salary only as a tiebreak among equal/missing projections", () => {
    const rows = [
      row({ id: "1", team: "PHI", name: "Low Proj High Salary", salary: 9000, projection: 1 }),
      row({ id: "2", team: "PHI", name: "High Proj Low Salary", salary: 3000, projection: 15 }),
    ];
    const summaries = buildStackSummaries(rows, {});
    const phi = summaries.find((s) => s.team === "PHI")!;
    expect(phi.top5[0].name).toBe("High Proj Low Salary");
  });
});

// ---------------------------------------------------------------------------
// MLB DASHBOARD INTELLIGENCE: Top Stacks / Best Value Stack
// ---------------------------------------------------------------------------

describe("buildStackCandidates", () => {
  it("builds a real N-man candidate from each team's already-selected top5, with totals matching the exact hitters included", () => {
    const rows = [
      row({ id: "1", team: "PHI", name: "A", salary: 4000, projection: 10, ceiling: 18, ownership: 20, leverage: 5 }),
      row({ id: "2", team: "PHI", name: "B", salary: 3000, projection: 8, ceiling: 14, ownership: 10, leverage: 3 }),
    ];
    const stacks = buildStackSummaries(rows, {});
    const [candidate] = buildStackCandidates(stacks);
    expect(candidate.team).toBe("PHI");
    expect(candidate.stackSize).toBe(2);
    expect(candidate.totalSalary).toBe(7000);
    expect(candidate.totalProjection).toBe(18);
    expect(candidate.totalCeiling).toBe(32);
    expect(candidate.averageOwnership).toBe(15);
    expect(candidate.averageLeverage).toBe(4);
    expect(candidate.value).toBeCloseTo((18 / 7000) * 1000, 2);
  });

  it("honestly reflects fewer than the requested size rather than fabricating placeholder hitters", () => {
    const rows = [row({ id: "1", team: "PHI", projection: 10 })];
    const stacks = buildStackSummaries(rows, {});
    const [candidate] = buildStackCandidates(stacks, 5);
    expect(candidate.requestedSize).toBe(5);
    expect(candidate.stackSize).toBe(1);
    expect(candidate.hitters).toHaveLength(1);
  });

  it("a 3-man/4-man view is just a re-slice of the same top5, never a new selection", () => {
    const rows = Array.from({ length: 5 }, (_, i) => row({ id: String(i), team: "PHI", projection: 10 - i }));
    const stacks = buildStackSummaries(rows, {});
    const [c5] = buildStackCandidates(stacks, 5);
    const [c3] = buildStackCandidates(stacks, 3);
    expect(c3.hitters.map((h) => h.id)).toEqual(c5.hitters.slice(0, 3).map((h) => h.id));
  });

  it("drops teams with zero eligible hitters entirely -- never a fabricated empty stack", () => {
    const rows = [row({ id: "1", team: "LAD", optimizerEligible: false, projection: null, eligibilityStatus: "LINEUP_UNCONFIRMED" })];
    const stacks = buildStackSummaries(rows, {});
    expect(buildStackCandidates(stacks)).toEqual([]);
  });

  it("totalSalary/totalProjection are null (never partially fabricated) unless every included hitter has a real value", () => {
    const rows = [
      row({ id: "1", team: "PHI", salary: 4000, projection: 10 }),
      row({ id: "2", team: "PHI", salary: null, projection: null, eligibilityStatus: "PROBABLE_HITTER" }),
    ];
    const stacks = buildStackSummaries(rows, {});
    const [candidate] = buildStackCandidates(stacks);
    expect(candidate.totalSalary).toBeNull();
    expect(candidate.totalProjection).toBeNull();
    expect(candidate.value).toBeNull();
  });
});

describe("buildStackCandidates -- probable starters and bench/out exclusion (Phase 3/12)", () => {
  it("includes a real PROBABLE_HITTER before official lineups post (optimizerEligible is the authoritative signal)", () => {
    const rows = [row({ id: "1", team: "LAD", name: "Probable Guy", eligibilityStatus: "PROBABLE_HITTER", optimizerEligible: true, projection: 9 })];
    const stacks = buildStackSummaries(rows, {});
    const [candidate] = buildStackCandidates(stacks);
    expect(candidate.hitters.map((h) => h.name)).toEqual(["Probable Guy"]);
  });

  it("never includes a BENCH/OUT/SCRATCHED hitter in the stack, even if their raw projection would otherwise rank #1", () => {
    const rows = [
      row({ id: "1", team: "LAD", name: "Confirmed Starter", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true, projection: 8 }),
      row({ id: "2", team: "LAD", name: "Scratched Star", eligibilityStatus: "SCRATCHED", optimizerEligible: false, projection: 30 }),
    ];
    const stacks = buildStackSummaries(rows, {});
    const [candidate] = buildStackCandidates(stacks);
    expect(candidate.hitters.map((h) => h.name)).toEqual(["Confirmed Starter"]);
  });
});

describe("stackScore -- the Big Money Stack Score", () => {
  it("rewards production and ceiling equally as its primary component", () => {
    const rows = [row({ id: "1", team: "PHI", salary: 4000, projection: 20, ceiling: 40 })];
    const stacks = buildStackSummaries(rows, {});
    const [candidate] = buildStackCandidates(stacks);
    // (20 + 40) / 2 = 30 primary, plus a value bonus (5.0 pts/$1k * 2 = 10); no depth bonus (exactly 1 eligible hitter for 1 stack slot)
    expect(stackScore(candidate)).toBe(40);
  });

  it("never lets ownership/leverage alone change the score -- it isn't a ranking input", () => {
    const lowOwned = buildStackCandidates(buildStackSummaries([row({ id: "1", team: "A", salary: 4000, projection: 20, ceiling: 40, ownership: 2 })], {}))[0];
    const highOwned = buildStackCandidates(buildStackSummaries([row({ id: "1", team: "B", salary: 4000, projection: 20, ceiling: 40, ownership: 90 })], {}))[0];
    expect(stackScore(lowOwned)).toBe(stackScore(highOwned));
  });

  it("returns null (never a fabricated 0) when production/ceiling totals are unavailable", () => {
    const rows = [row({ id: "1", team: "PHI", salary: null, projection: null, ceiling: null, eligibilityStatus: "PROBABLE_HITTER" })];
    const stacks = buildStackSummaries(rows, {});
    const [candidate] = buildStackCandidates(stacks);
    expect(stackScore(candidate)).toBeNull();
  });
});

describe("rankStackCandidatesByScore -- Top Stacks", () => {
  it("ranks a real, higher-production stack above a cheaper but weaker one", () => {
    const strongStack = buildStackSummaries(
      [row({ id: "1", team: "STRONG", salary: 5000, projection: 15, ceiling: 25 }), row({ id: "2", team: "STRONG", salary: 5000, projection: 15, ceiling: 25 })],
      {},
    );
    const weakStack = buildStackSummaries(
      [row({ id: "3", team: "WEAK", salary: 3000, projection: 5, ceiling: 9 }), row({ id: "4", team: "WEAK", salary: 3000, projection: 5, ceiling: 9 })],
      {},
    );
    const candidates = [...buildStackCandidates(strongStack), ...buildStackCandidates(weakStack)];
    const ranked = rankStackCandidatesByScore(candidates);
    expect(ranked.map((c) => c.team)).toEqual(["STRONG", "WEAK"]);
  });

  it("excludes a single-hitter 'stack' -- not a real stack in DFS terms", () => {
    const rows = [row({ id: "1", team: "SOLO", projection: 50, ceiling: 80 })];
    const candidates = buildStackCandidates(buildStackSummaries(rows, {}));
    expect(rankStackCandidatesByScore(candidates)).toEqual([]);
  });

  it("returns an empty list (never fabricated) when there are no real stack candidates yet", () => {
    expect(rankStackCandidatesByScore([])).toEqual([]);
  });
});

describe("rankStackCandidatesByValue -- Best Value Stack", () => {
  it("ranks the strongest production-per-dollar stack first, even when it isn't the top-scored stack", () => {
    const bigButExpensive = buildStackSummaries(
      [row({ id: "1", team: "EXPENSIVE", salary: 10000, projection: 40, ceiling: 60 }), row({ id: "2", team: "EXPENSIVE", salary: 10000, projection: 40, ceiling: 60 })],
      {},
    );
    const cheapAndEfficient = buildStackSummaries(
      [row({ id: "3", team: "VALUE", salary: 3000, projection: 20, ceiling: 30 }), row({ id: "4", team: "VALUE", salary: 3000, projection: 20, ceiling: 30 })],
      {},
    );
    const candidates = [...buildStackCandidates(bigButExpensive), ...buildStackCandidates(cheapAndEfficient)];
    const ranked = rankStackCandidatesByValue(candidates);
    expect(ranked[0].team).toBe("VALUE");
  });
});
