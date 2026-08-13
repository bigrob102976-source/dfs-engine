import { describe, expect, it } from "vitest";

import { buildHitterRows, buildPitcherRows } from "../normalize";
import type { BatterRecord, DKPlayerPool, OwnershipSnapshot, PitcherRecord } from "../types";

function pitcher(overrides: Partial<PitcherRecord> = {}): PitcherRecord {
  return {
    player_id: "1001",
    name: "Test Pitcher",
    team: "TOR",
    opponent: "BOS",
    projection: 20.0,
    ceiling: 30.0,
    overall_score: 75.0,
    risk_score: 30.0,
    confidence: 90.0,
    tags: ["elite_k_upside"],
    reasons: ["reason one"],
    ...overrides,
  };
}

function ownershipSnapshot(): OwnershipSnapshot {
  return {
    slate_date: "2026-08-11",
    model_version: "0.1.0",
    player_count: 1,
    players: [
      {
        dk_player_id: "d1",
        mlb_player_id: "1001",
        name: "Test Pitcher",
        team: "TOR",
        opponent: "BOS",
        player_type: "pitcher",
        dk_positions: ["P"],
        salary: 9500,
        projection: 20.0,
        ceiling: 30.0,
        overall_score: 75.0,
        risk_score: 30.0,
        confidence: 90.0,
        projected_ownership: 42.5,
        ownership_confidence: 88.0,
        chalk_score: 70.0,
        leverage_score: 12.5,
        ownership_tier: "very_high",
        batting_order: null,
        feature_breakdown: {},
        reasons: [],
        tags: ["chalk"],
        model_version: "0.1.0",
      },
    ],
    team_popularity: {},
    normalization_checks: {},
  };
}

function pool(): DKPlayerPool {
  return {
    slate_date: "2026-08-11",
    generated_at_utc: "2026-08-11T18:00:00Z",
    pitcher_snapshot_path: null,
    batter_snapshot_path: null,
    player_count: 1,
    players: [
      {
        dk_player_id: "d1",
        name: "Test Pitcher",
        team: "TOR",
        player_type: "pitcher",
        dk_positions: ["P"],
        salary: 9500,
        mlb_player_id: "1001",
        opponent: "BOS",
        game_id: "g1",
        batting_order: null,
        projection: 20.0,
        ceiling: 30.0,
        floor: 12.0,
        overall_score: 75.0,
        risk_score: 30.0,
        confidence: 90.0,
        tags: [],
        reasons: [],
        season_sample_size: null,
        lineup_status: "active",
        match_status: "matched",
      },
    ],
  };
}

describe("buildPitcherRows", () => {
  it("joins pitcher snapshot with ownership and pool by mlb_player_id", () => {
    const rows = buildPitcherRows([pitcher()], ownershipSnapshot(), pool());
    expect(rows).toHaveLength(1);
    expect(rows[0].ownership).toBe(42.5);
    expect(rows[0].leverage).toBe(12.5);
    expect(rows[0].salary).toBe(9500);
    expect(rows[0].playerType).toBe("pitcher");
  });

  it("leaves ownership/leverage null when no ownership snapshot is loaded", () => {
    const rows = buildPitcherRows([pitcher()], null, null);
    expect(rows[0].ownership).toBeNull();
    expect(rows[0].leverage).toBeNull();
    expect(rows[0].salary).toBeNull();
  });

  it("never invents a value for an unmatched player", () => {
    const rows = buildPitcherRows([pitcher({ player_id: "9999" })], ownershipSnapshot(), pool());
    expect(rows[0].ownership).toBeNull();
    expect(rows[0].salary).toBeNull();
  });
});

describe("buildHitterRows", () => {
  function hitter(overrides: Partial<BatterRecord> = {}): BatterRecord {
    return {
      player_id: "2001",
      name: "Test Hitter",
      team: "PHI",
      opponent: "STL",
      batting_order: 3,
      position: "OF",
      projection: 8.0,
      ceiling: 15.0,
      overall_score: 65.0,
      risk_score: 25.0,
      confidence: 95.0,
      tags: [],
      reasons: [],
      ...overrides,
    };
  }

  it("uses the DK pool's multi-position eligibility over the snapshot's single position", () => {
    const poolWithMultiPos = pool();
    poolWithMultiPos.players[0] = {
      ...poolWithMultiPos.players[0],
      dk_player_id: "d2",
      mlb_player_id: "2001",
      player_type: "hitter",
      dk_positions: ["1B", "OF"],
    };
    const rows = buildHitterRows([hitter()], null, poolWithMultiPos);
    expect(rows[0].positions).toEqual(["1B", "OF"]);
    expect(rows[0].position).toBe("1B");
  });

  it("falls back to the snapshot position when no pool is loaded", () => {
    const rows = buildHitterRows([hitter()], null, null);
    expect(rows[0].position).toBe("OF");
    expect(rows[0].positions).toEqual(["OF"]);
  });

  it("carries batting order through", () => {
    const rows = buildHitterRows([hitter({ batting_order: 2 })], null, null);
    expect(rows[0].battingOrder).toBe(2);
  });
});
