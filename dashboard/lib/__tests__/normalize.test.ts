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

  it("defaults mlProjection/mlProjectionStatus to null when no ML map is passed", () => {
    const rows = buildHitterRows([hitter()], null, null);
    expect(rows[0].mlProjection).toBeNull();
    expect(rows[0].mlProjectionStatus).toBeNull();
  });

  it("joins a valid pregame ML projection by player_id", () => {
    const mlByPlayerId = new Map([
      ["2001", { player_id: "2001", dk_player_id: null, name: "Test Hitter", team: "PHI", opponent: "STL", game_id: null, salary: null, projection: 10.8, model_version: "1.0.0", data_quality_score: 0.98, feature_coverage: 0.99, missing_features: [], projection_status: "LIVE_PREGAME" as const, feature_timestamp: null, game_scheduled_start_utc: null, warnings: [] }],
    ]);
    const rows = buildHitterRows([hitter()], null, null, mlByPlayerId);
    expect(rows[0].mlProjection).toBe(10.8);
    expect(rows[0].mlProjectionStatus).toBe("LIVE_PREGAME");
  });

  it("never surfaces a MISSING/INVALID_FEATURE_PARITY ML projection value, only the status", () => {
    const mlByPlayerId = new Map([
      ["2001", { player_id: "2001", dk_player_id: null, name: "Test Hitter", team: "PHI", opponent: "STL", game_id: null, salary: null, projection: null, model_version: "1.0.0", data_quality_score: null, feature_coverage: null, missing_features: [], projection_status: "MISSING" as const, feature_timestamp: null, game_scheduled_start_utc: null, warnings: [] }],
    ]);
    const rows = buildHitterRows([hitter()], null, null, mlByPlayerId);
    expect(rows[0].mlProjection).toBeNull();
    expect(rows[0].mlProjectionStatus).toBe("MISSING");
  });
});

// ----------------------------------------------------------------------------
// Milestone 27.2 -- CONFIRMED real bug: a DK-salaried player whose team's
// lineup hasn't posted yet (live example, 2026-08-18: all 52 real LAD @
// COL DraftKings rows) never got a row at all, because these functions
// used to iterate ONLY the research board (confirmed-lineup-only data).
// A real MLB team could silently vanish from every page built on
// buildPitcherRows/buildHitterRows (Command Center, Pitchers, Hitters,
// Stacks, Projection Lab) even though the DK pool had them the whole
// time. Regression fixture modeled on the exact real shape.
// ----------------------------------------------------------------------------

function unconfirmedPoolHitter(overrides: Partial<import("../types").DFSPlayer> = {}): import("../types").DFSPlayer {
  return {
    dk_player_id: "d-lad-1",
    name: "Shohei Ohtani",
    team: "LAD",
    player_type: "hitter",
    dk_positions: ["1B", "OF"],
    salary: 7100,
    mlb_player_id: null,
    opponent: "COL",
    game_id: "824319",
    batting_order: null,
    projection: null,
    ceiling: null,
    floor: null,
    overall_score: null,
    risk_score: null,
    confidence: null,
    tags: [],
    reasons: [],
    season_sample_size: null,
    lineup_status: "lineup_not_confirmed",
    match_status: "unmatched",
    ...overrides,
  };
}

describe("Milestone 27.2: DK-pool player preservation", () => {
  it("preserves a DK pool hitter with no board match instead of dropping the row (LAD @ COL regression)", () => {
    const poolWithLad = pool();
    poolWithLad.players = [unconfirmedPoolHitter()];
    const rows = buildHitterRows([], null, poolWithLad);

    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe("Shohei Ohtani");
    expect(rows[0].team).toBe("LAD");
    expect(rows[0].salary).toBe(7100);
  });

  it("never invents a projection for a preserved unconfirmed-lineup player", () => {
    const poolWithLad = pool();
    poolWithLad.players = [unconfirmedPoolHitter()];
    const rows = buildHitterRows([], null, poolWithLad);

    expect(rows[0].projection).toBeNull();
    expect(rows[0].ceiling).toBeNull();
    expect(rows[0].floor).toBeNull();
  });

  it("carries lineupStatus/matchStatus through so a page can label the row honestly", () => {
    const poolWithLad = pool();
    poolWithLad.players = [unconfirmedPoolHitter()];
    const rows = buildHitterRows([], null, poolWithLad);

    expect(rows[0].lineupStatus).toBe("lineup_not_confirmed");
    expect(rows[0].matchStatus).toBe("unmatched");
  });

  it("preserves a scratched player with an explicit scratched status", () => {
    const poolWithScratch = pool();
    poolWithScratch.players = [unconfirmedPoolHitter({ dk_player_id: "d-lad-2", name: "Scratched Player", lineup_status: "scratched" })];
    const rows = buildHitterRows([], null, poolWithScratch);

    expect(rows).toHaveLength(1);
    expect(rows[0].lineupStatus).toBe("scratched");
  });

  it("does NOT duplicate a player already matched from the board", () => {
    const matchedHitter = hitterFixture();
    const poolWithMatch = pool();
    poolWithMatch.players = [
      { ...unconfirmedPoolHitter(), dk_player_id: "d-2001", mlb_player_id: "2001", lineup_status: "active", match_status: "matched" },
    ];
    const rows = buildHitterRows([matchedHitter], null, poolWithMatch);
    expect(rows).toHaveLength(1);
  });

  it("Dodgers full-team regression: every real DK row for a team with no posted lineup is preserved, none fabricated", () => {
    const ladPlayers = ["Shohei Ohtani", "Freddie Freeman", "Mookie Betts", "Will Smith", "Tyler Glasnow"].map((name, i) =>
      unconfirmedPoolHitter({ dk_player_id: `d-lad-${i}`, name }),
    );
    const poolWithFullLad = pool();
    poolWithFullLad.players = ladPlayers;
    const rows = buildHitterRows([], null, poolWithFullLad);

    expect(rows).toHaveLength(5);
    expect(rows.every((r) => r.team === "LAD")).toBe(true);
    expect(rows.every((r) => r.projection === null)).toBe(true);
    expect(rows.map((r) => r.name)).toEqual(expect.arrayContaining(["Shohei Ohtani", "Freddie Freeman", "Mookie Betts"]));
  });

  it("pitcher-side: preserves an unmatched DK pitcher row the same way", () => {
    const poolWithPitcher = pool();
    poolWithPitcher.players = [
      { ...unconfirmedPoolHitter(), dk_player_id: "d-lad-p1", name: "Tyler Glasnow", player_type: "pitcher", dk_positions: ["P"] },
    ];
    const rows = buildPitcherRows([], null, poolWithPitcher);
    expect(rows).toHaveLength(1);
    expect(rows[0].name).toBe("Tyler Glasnow");
    expect(rows[0].playerType).toBe("pitcher");
    expect(rows[0].projection).toBeNull();
  });

  it("assigns a stable, mlb-id-free identity to an unmatched player (never a raw DK id collision risk across slates)", () => {
    const poolWithLad = pool();
    poolWithLad.players = [unconfirmedPoolHitter({ dk_player_id: "1006" })];
    const rows = buildHitterRows([], null, poolWithLad);
    expect(rows[0].id).toBe("dk:1006");
    expect(rows[0].id).not.toBe("1006");
  });
});

function hitterFixture(): BatterRecord {
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
  };
}
