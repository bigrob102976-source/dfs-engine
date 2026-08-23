import { describe, expect, it } from "vitest";

import type { BlueCollarPlayerProjection, BlueCollarSnapshot } from "../blueCollarProjections";
import type { MlCoverageSummary, NativeRankedPlayer } from "../commandCenter";
import {
  buildSlateReadinessSummary,
  buildTeamReadinessRows,
  computeSlateCompletionStage,
} from "../slateReadiness";
import type { PlayerRow, ResearchGame } from "../types";

function row(overrides: Partial<PlayerRow> = {}): PlayerRow {
  return {
    id: "1", playerType: "hitter", name: "Player", team: "NYY", opponent: "BOS", gameId: "g1",
    position: "OF", positions: ["OF"], battingOrder: null, salary: 4000, projection: 8, ceiling: 15, floor: 4,
    overall: null, power: null, matchup: null, risk: null, confidence: null, ownership: null, ownershipTier: null,
    chalkScore: null, leverage: null, tags: [], reasons: [], lineupStatus: null, matchStatus: "matched",
    eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false, mlProjection: null, mlProjectionStatus: null,
    blueCollarProjection: null, blueCollarMatchStatus: null, raw: { snapshot: {}, ownership: null, pool: null },
    ...overrides,
  };
}

function nativeRow(overrides: Partial<NativeRankedPlayer> = {}): NativeRankedPlayer {
  return { ...row(), nativeProjection: null, nativeDelta: null, nativeConfidence: null, ...overrides };
}

function bcPlayer(overrides: Partial<BlueCollarPlayerProjection> = {}): BlueCollarPlayerProjection {
  return {
    bluecollar_local_id: "x", name: "X", team: "NYY", position: "OF", opponent: "BOS", salary: 4000,
    raw_projection: 9, usable_projection: 9, match_status: "matched", match_confidence: "name_team_exact",
    mlb_player_id: "1", candidate_mlb_ids: [], candidate_names: [],
    ...overrides,
  };
}

function bcSnapshot(players: BlueCollarPlayerProjection[]): BlueCollarSnapshot {
  return {
    slate_date: "2026-08-23", dk_slate_id: "dk-1", bluecollar_slate_id: "bc-1", bluecollar_slate_name: "Main",
    bluecollar_updated: "12:00 ET", retrieved_at: "2026-08-23T18:00:00Z", slate_match_status: "matched",
    slate_match_reason: null, player_count: players.length,
    matched_count: players.filter((p) => p.match_status === "matched").length,
    usable_projection_count: players.filter((p) => p.usable_projection !== null).length,
    players,
  };
}

function mlCoverage(overrides: Partial<MlCoverageSummary> = {}): MlCoverageSummary {
  return { eligiblePitchers: 0, projectedPitchers: 0, eligibleHitters: 0, projectedHitters: 0, ...overrides };
}

describe("buildSlateReadinessSummary", () => {
  it("reads dk players / identity resolved directly from the match report", () => {
    const summary = buildSlateReadinessSummary(
      { dk_entries: 746, matched_to_mlb: 415, eligibility: {}, teams_awaiting_lineups: [] },
      [], [], [], [], mlCoverage(), null,
    );
    expect(summary.dkPlayers).toBe(746);
    expect(summary.identityResolved).toBe(415);
  });

  it("computes starting pitchers as confirmed-count / total pitcher rows", () => {
    const pitcherRows = [row({ id: "p1", playerType: "pitcher" }), row({ id: "p2", playerType: "pitcher" })];
    const summary = buildSlateReadinessSummary(
      { eligibility: { starting_pitchers: 1 }, teams_awaiting_lineups: [] },
      [], pitcherRows, [], [], mlCoverage(), null,
    );
    expect(summary.startingPitchers).toEqual({ covered: 1, eligible: 2 });
  });

  it("computes lineups confirmed as total teams minus teams awaiting lineups", () => {
    const summary = buildSlateReadinessSummary(
      { eligibility: {}, teams_awaiting_lineups: ["TOR", "BOS"] },
      ["NYY", "TOR", "BOS", "PHI"], [], [], [], mlCoverage(), null,
    );
    expect(summary.lineupsConfirmed).toEqual({ covered: 2, eligible: 4 });
  });

  it("reads blueCollarUsable from the snapshot's own usable_projection_count", () => {
    const summary = buildSlateReadinessSummary(null, [], [], [], [], mlCoverage(), bcSnapshot([bcPlayer(), bcPlayer({ mlb_player_id: "2", usable_projection: null })]));
    expect(summary.blueCollarUsable).toBe(1);
  });

  it("computes native/AI eligible coverage from optimizerEligible rows only", () => {
    const nativeRows = [
      nativeRow({ id: "1", optimizerEligible: true, nativeProjection: 10 }),
      nativeRow({ id: "2", optimizerEligible: true, nativeProjection: null }),
      nativeRow({ id: "3", optimizerEligible: false, nativeProjection: null }), // not eligible -- excluded entirely
    ];
    const summary = buildSlateReadinessSummary(null, [], [], nativeRows, [], mlCoverage(), null);
    expect(summary.nativeEligible).toEqual({ covered: 1, eligible: 2 });
  });

  it("computes ML eligible coverage from the existing ML coverage summary, pitchers + hitters combined", () => {
    const summary = buildSlateReadinessSummary(
      null, [], [], [], [], mlCoverage({ eligiblePitchers: 5, projectedPitchers: 3, eligibleHitters: 10, projectedHitters: 8 }), null,
    );
    expect(summary.mlEligible).toEqual({ covered: 11, eligible: 15 });
  });

  it("reads optimizer eligible from the match report's own eligibility count", () => {
    const summary = buildSlateReadinessSummary({ eligibility: { optimizer_eligible: 15 } }, [], [], [], [], mlCoverage(), null);
    expect(summary.optimizerEligible).toBe(15);
  });

  it("never crashes on a null match report -- every count degrades to 0/empty honestly", () => {
    const summary = buildSlateReadinessSummary(null, [], [], [], [], mlCoverage(), null);
    expect(summary.dkPlayers).toBe(0);
    expect(summary.identityResolved).toBe(0);
    expect(summary.optimizerEligible).toBe(0);
  });
});

describe("buildTeamReadinessRows", () => {
  it("marks a team CONFIRMED once it has a real STARTING_HITTER row, UNCONFIRMED otherwise", () => {
    const hitterRows = [
      row({ id: "h1", team: "PHI", eligibilityStatus: "STARTING_HITTER", optimizerEligible: true }),
      row({ id: "h2", team: "TOR", eligibilityStatus: "LINEUP_UNCONFIRMED", optimizerEligible: false }),
    ];
    const rows = buildTeamReadinessRows(["PHI", "TOR"], [], hitterRows, [], [], null, new Set(), new Map());
    expect(rows.find((r) => r.team === "PHI")!.lineupStatus).toBe("CONFIRMED");
    expect(rows.find((r) => r.team === "TOR")!.lineupStatus).toBe("UNCONFIRMED");
  });

  it("marks starterStatus CONFIRMED only when a real STARTING_PITCHER row exists for that team", () => {
    const pitcherRows = [row({ id: "p1", playerType: "pitcher", team: "PHI", eligibilityStatus: "STARTING_PITCHER" })];
    const rows = buildTeamReadinessRows(["PHI"], pitcherRows, [], [], [], null, new Set(), new Map());
    expect(rows[0].starterStatus).toBe("CONFIRMED");
  });

  it("marks blueCollar AVAILABLE only when this team has a usable BlueCollar projection", () => {
    const snapshot = bcSnapshot([bcPlayer({ team: "PHI", usable_projection: 9 }), bcPlayer({ team: "TOR", usable_projection: null })]);
    const rows = buildTeamReadinessRows(["PHI", "TOR"], [], [], [], [], snapshot, new Set(), new Map());
    expect(rows.find((r) => r.team === "PHI")!.blueCollar).toBe("AVAILABLE");
    expect(rows.find((r) => r.team === "TOR")!.blueCollar).toBe("PENDING");
  });

  it("marks native/ai GENERATED only when every eligible team player has a value", () => {
    const nativeRows = [nativeRow({ id: "1", team: "PHI", optimizerEligible: true, nativeProjection: 10 })];
    const rows = buildTeamReadinessRows(["PHI"], [], [], nativeRows, [], null, new Set(), new Map());
    expect(rows[0].native).toBe("GENERATED");
  });

  it("marks native PENDING when no eligible team player has a value yet, or none are eligible", () => {
    const nativeRows = [nativeRow({ id: "1", team: "PHI", optimizerEligible: true, nativeProjection: null })];
    const rows = buildTeamReadinessRows(["PHI"], [], [], nativeRows, [], null, new Set(), new Map());
    expect(rows[0].native).toBe("PENDING");
  });

  it("marks ownership GENERATED only when every eligible team player is in the ownership set", () => {
    const hitterRows = [row({ id: "h1", team: "PHI", optimizerEligible: true })];
    const withOwnership = buildTeamReadinessRows(["PHI"], [], hitterRows, [], [], null, new Set(["h1"]), new Map());
    const withoutOwnership = buildTeamReadinessRows(["PHI"], [], hitterRows, [], [], null, new Set(), new Map());
    expect(withOwnership[0].ownership).toBe("GENERATED");
    expect(withoutOwnership[0].ownership).toBe("PENDING");
  });

  it("reuses lib/stacks.ts's own per-team status verbatim for stackReady, never recomputing it", () => {
    const rows = buildTeamReadinessRows(["PHI", "TOR"], [], [], [], [], null, new Set(), new Map([["PHI", "CONFIRMED"]]));
    expect(rows.find((r) => r.team === "PHI")!.stackReady).toBe("READY");
    expect(rows.find((r) => r.team === "TOR")!.stackReady).toBe("WAITING");
  });

  it("returns rows sorted alphabetically by team", () => {
    const rows = buildTeamReadinessRows(["TOR", "BOS", "AZ"], [], [], [], [], null, new Set(), new Map());
    expect(rows.map((r) => r.team)).toEqual(["AZ", "BOS", "TOR"]);
  });
});

function game(overrides: Partial<ResearchGame> = {}): ResearchGame {
  return {
    game_id: "g1", date: "2026-08-23", game_datetime_utc: "2026-08-23T23:05:00Z", status: "Scheduled",
    home_team_abbr: "BOS", away_team_abbr: "TOR", venue_name: null,
    home_probable_pitcher_id: null, away_probable_pitcher_id: null, game_number: 1,
    ...overrides,
  };
}

function readiness(overrides: Partial<ReturnType<typeof buildSlateReadinessSummary>> = {}) {
  return {
    dkPlayers: 746, identityResolved: 415, startingPitchers: { covered: 15, eligible: 419 },
    lineupsConfirmed: { covered: 0, eligible: 15 }, blueCollarUsable: 159,
    nativeEligible: { covered: 15, eligible: 15 }, aiEligible: { covered: 15, eligible: 15 },
    mlEligible: { covered: 15, eligible: 15 }, optimizerEligible: 15,
    ...overrides,
  };
}

describe("computeSlateCompletionStage", () => {
  it("classifies EARLY when no team has a confirmed lineup yet", () => {
    const stage = computeSlateCompletionStage(readiness({ lineupsConfirmed: { covered: 0, eligible: 15 } }), [game()], null);
    expect(stage).toBe("EARLY");
  });

  it("classifies PARTIAL_LINEUPS when fewer than half of teams are confirmed", () => {
    const stage = computeSlateCompletionStage(readiness({ lineupsConfirmed: { covered: 2, eligible: 15 } }), [game()], null);
    expect(stage).toBe("PARTIAL_LINEUPS");
  });

  it("classifies MOSTLY_READY once at least half of teams are confirmed but not all", () => {
    const stage = computeSlateCompletionStage(readiness({ lineupsConfirmed: { covered: 8, eligible: 15 } }), [game()], null);
    expect(stage).toBe("MOSTLY_READY");
  });

  it("classifies READY once every team is confirmed and the optimizer pool is non-empty", () => {
    const stage = computeSlateCompletionStage(
      readiness({ lineupsConfirmed: { covered: 15, eligible: 15 }, optimizerEligible: 146 }), [game()], null,
    );
    expect(stage).toBe("READY");
  });

  it("classifies MOSTLY_READY (not READY) when all teams confirmed but the optimizer pool is still empty", () => {
    const stage = computeSlateCompletionStage(
      readiness({ lineupsConfirmed: { covered: 15, eligible: 15 }, optimizerEligible: 0 }), [game()], null,
    );
    expect(stage).toBe("MOSTLY_READY");
  });

  it("classifies LOCKED once the earliest real DK lock time has passed, regardless of lineup coverage", () => {
    const stage = computeSlateCompletionStage(
      readiness({ lineupsConfirmed: { covered: 0, eligible: 15 } }), [game()], "2026-08-23T18:00:00Z", "2026-08-23T18:05:00Z",
    );
    expect(stage).toBe("LOCKED");
  });

  it("classifies IN_PROGRESS from real MLB game status, even before the computed lock time check", () => {
    const stage = computeSlateCompletionStage(readiness(), [game({ status: "In Progress" })], null);
    expect(stage).toBe("IN_PROGRESS");
  });

  it("classifies FINAL only once every real game's status is final", () => {
    const stage = computeSlateCompletionStage(
      readiness(), [game({ game_id: "g1", status: "Final" }), game({ game_id: "g2", status: "Final" })], null,
    );
    expect(stage).toBe("FINAL");
  });

  it("does not classify FINAL when only some games have finished", () => {
    const stage = computeSlateCompletionStage(
      readiness(), [game({ game_id: "g1", status: "Final" }), game({ game_id: "g2", status: "Scheduled" })], null,
    );
    expect(stage).not.toBe("FINAL");
  });
});
