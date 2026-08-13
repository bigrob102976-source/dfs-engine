import { describe, expect, it } from "vitest";

import { buildStackSummaries } from "../stacks";
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
    raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

describe("buildStackSummaries", () => {
  it("groups hitters by team and averages their metrics", () => {
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
});
