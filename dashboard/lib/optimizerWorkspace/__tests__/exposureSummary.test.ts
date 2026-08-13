import { describe, expect, it } from "vitest";

import { buildExposureRows, buildStackExposureRows } from "../exposureSummary";
import type { Lineup, LineupAssignment } from "../../types";

function assignment(overrides: Partial<LineupAssignment> = {}): LineupAssignment {
  return {
    slot: "OF",
    dk_player_id: "d1",
    mlb_player_id: "h1",
    name: "Player A",
    team: "PHI",
    opponent: "NYM",
    salary: 4000,
    projection: 10,
    ceiling: 18,
    floor: 5,
    risk_score: 30,
    confidence: 80,
    projected_ownership: null,
    ...overrides,
  };
}

function lineup(overrides: Partial<Lineup> = {}): Lineup {
  return {
    index: 1,
    assignments: [assignment()],
    salary: 40000,
    remaining_salary: 10000,
    projection: 100,
    ceiling: 180,
    floor: 50,
    average_risk: 30,
    average_confidence: 80,
    team_counts: {},
    primary_stack_team: "PHI",
    primary_stack_size: 5,
    sum_ownership: null,
    average_ownership: null,
    max_ownership: null,
    players_above_chalk_threshold: null,
    ...overrides,
  };
}

describe("buildExposureRows", () => {
  it("returns [] for an empty lineup set", () => {
    expect(buildExposureRows([])).toEqual([]);
  });

  it("counts each player's appearances and computes exposure percent", () => {
    const lineups = [
      lineup({ index: 1, assignments: [assignment({ dk_player_id: "d1", name: "A" }), assignment({ dk_player_id: "d2", name: "B", slot: "P" })] }),
      lineup({ index: 2, assignments: [assignment({ dk_player_id: "d1", name: "A" })] }),
      lineup({ index: 3, assignments: [assignment({ dk_player_id: "d1", name: "A" }), assignment({ dk_player_id: "d3", name: "C" })] }),
    ];
    const rows = buildExposureRows(lineups);
    const byName = Object.fromEntries(rows.map((r) => [r.name, r]));
    expect(byName.A).toEqual({ name: "A", team: "PHI", playerType: "hitter", lineups: 3, exposurePercent: 100 });
    expect(byName.B).toEqual({ name: "B", team: "PHI", playerType: "pitcher", lineups: 1, exposurePercent: 33 });
    expect(byName.C).toEqual({ name: "C", team: "PHI", playerType: "hitter", lineups: 1, exposurePercent: 33 });
    // Sorted descending by exposure.
    expect(rows[0].name).toBe("A");
  });

  it("filters to pitchers only when requested (slot P)", () => {
    const lineups = [
      lineup({
        assignments: [assignment({ dk_player_id: "d1", name: "Hitter", slot: "OF" }), assignment({ dk_player_id: "d2", name: "Pitcher", slot: "P" })],
      }),
    ];
    const rows = buildExposureRows(lineups, "pitcher");
    expect(rows.map((r) => r.name)).toEqual(["Pitcher"]);
  });
});

describe("buildStackExposureRows", () => {
  it("returns [] for an empty lineup set", () => {
    expect(buildStackExposureRows([])).toEqual([]);
  });

  it("counts primary_stack_team occurrences and skips lineups with no stack", () => {
    const lineups = [
      lineup({ primary_stack_team: "PHI" }),
      lineup({ primary_stack_team: "PHI" }),
      lineup({ primary_stack_team: "NYY" }),
      lineup({ primary_stack_team: null }),
    ];
    const rows = buildStackExposureRows(lineups);
    expect(rows).toEqual([
      { team: "PHI", lineups: 2, exposurePercent: 50 },
      { team: "NYY", lineups: 1, exposurePercent: 25 },
    ]);
  });
});
