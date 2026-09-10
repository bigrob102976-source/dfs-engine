import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { dkMatchReportFromCanonicalPool, dkPlayerPoolFromCanonicalPool, resolveDkBundle } from "../canonicalDkAdapter";
import type { OptimizerPoolResult, PoolPlayerRow } from "../optimizerWorkspace/types";

vi.mock("../loaders", () => ({
  loadLatestDKPlayerPool: vi.fn(),
  loadLatestDkMatchReport: vi.fn(),
  loadLatestProviderSlate: vi.fn(),
}));
vi.mock("../servingBackend/canonicalPostgresBackend", () => ({
  canonicalGetSlatePool: vi.fn(),
}));

function player(overrides: Partial<PoolPlayerRow> = {}): PoolPlayerRow {
  return {
    dkPlayerId: "d1",
    mlbPlayerId: "h1",
    name: "Leadoff Hitter",
    team: "BOS",
    opponent: "TOR",
    gameId: "g1",
    playerType: "hitter",
    positions: ["OF"],
    battingOrder: 1,
    salary: 4000,
    projection: 10,
    ceiling: 18,
    value: 2.5,
    ownership: null,
    leverage: null,
    risk: 30,
    confidence: 80,
    lineupStatus: "active",
    matchStatus: "matched",
    eligibilityStatus: "STARTING_HITTER",
    optimizerEligible: true,
    externalProjection: null,
    adjustedProjection: null,
    adjustmentDelta: null,
    adjustmentPercent: null,
    adjustmentReasons: [],
    aiProjection: null,
    aiCeiling: null,
    aiFloor: null,
    aiDelta: null,
    aiConfidence: null,
    aiRisk: null,
    aiGrade: null,
    aiValueScore: null,
    aiSignals: [],
    aiReasons: [],
    aiSummary: null,
    nativeProjection: null,
    nativeCeiling: null,
    nativeFloor: null,
    nativeDelta: null,
    nativeConfidence: null,
    nativeReasons: [],
    nativeExpectedPa: null,
    nativeExpectedInnings: null,
    nativeHitterComponents: null,
    nativePitcherComponents: null,
    fantasyProsProjection: null,
    fantasyProsMatchStatus: null,
    blueCollarProjection: null,
    blueCollarRawProjection: null,
    blueCollarMatchStatus: null,
    mlProjection: null,
    mlDataQualityScore: null,
    mlProjectionStatus: null,
    mlFeatureTimestamp: null,
    ...overrides,
  };
}

function pool(players: PoolPlayerRow[], overrides: Partial<OptimizerPoolResult> = {}): OptimizerPoolResult {
  return {
    date: "2026-09-09",
    slateId: "dkunofficial-153240",
    slateName: "Featured",
    providerName: "draftkings_unofficial_live",
    isMock: false,
    providerSource: "draftkings_unofficial_live",
    generatedAt: "2026-09-09T19:00:00Z",
    players,
    activePlayers: players.filter((p) => p.optimizerEligible).length,
    pitcherCount: players.filter((p) => p.playerType === "pitcher").length,
    hitterCount: players.filter((p) => p.playerType === "hitter").length,
    hasExternalProjections: false,
    externalProviderName: null,
    hasAiProjections: false,
    hasNativeProjections: true,
    hasFantasyProsProjections: false,
    hasMlProjections: false,
    hasBlueCollarProjections: false,
    blueCollarSlateName: null,
    blueCollarSlateMatchStatus: null,
    blueCollarUpdated: null,
    blueCollarCoverage: { returned: 0, usable: 0, identityResolved: 0, eligible: 0, optimizerReady: 0 },
    confirmedLineupGames: 0,
    unconfirmedLineupGames: 0,
    unmatchedCount: 0,
    slateGames: 1,
    rosterFeasibilityPass: true,
    salaryCap: 50000,
    hasOwnership: false,
    vegasCoverage: { dkGames: 0, pregameCovered: 0, missing: 0, frozen: 0, inPlayIgnored: 0, invalid: 0, notMatched: 0, coveragePercent: 0, primaryCovered: 0, fallbackCovered: 0, games: [] },
    dataStatus: "fresh",
    artifactAgeSeconds: 30,
    lastUpdatedAt: "2026-09-09T19:00:00Z",
    eligibilityComputedAt: "2026-09-09T19:00:00Z",
    ...overrides,
  };
}

describe("dkPlayerPoolFromCanonicalPool", () => {
  it("maps every field buildHitterRows/buildPitcherRows actually read", () => {
    const p = player({ dkPlayerId: "d1", mlbPlayerId: "h1", salary: 4500, eligibilityStatus: "STARTING_HITTER", optimizerEligible: true });
    const result = dkPlayerPoolFromCanonicalPool(pool([p]));

    expect(result.slate_date).toBe("2026-09-09");
    expect(result.selected_slate_id).toBe("dkunofficial-153240");
    expect(result.player_count).toBe(1);
    expect(result.players).toHaveLength(1);
    const dfsPlayer = result.players[0];
    expect(dfsPlayer.dk_player_id).toBe("d1");
    expect(dfsPlayer.mlb_player_id).toBe("h1");
    expect(dfsPlayer.salary).toBe(4500);
    expect(dfsPlayer.eligibility_status).toBe("STARTING_HITTER");
    expect(dfsPlayer.optimizer_eligible).toBe(true);
    expect(dfsPlayer.lineup_status).toBe(p.lineupStatus);
    expect(dfsPlayer.match_status).toBe(p.matchStatus);
  });

  it("never invents fields PoolPlayerRow doesn't carry (floor, tags, reasons, overall_score)", () => {
    const result = dkPlayerPoolFromCanonicalPool(pool([player()]));
    const dfsPlayer = result.players[0];
    expect(dfsPlayer.floor).toBeNull();
    expect(dfsPlayer.overall_score).toBeNull();
    expect(dfsPlayer.tags).toEqual([]);
    expect(dfsPlayer.reasons).toEqual([]);
  });

  it("carries an unresolved identity through as null, never a fabricated id", () => {
    const result = dkPlayerPoolFromCanonicalPool(pool([player({ mlbPlayerId: null })]));
    expect(result.players[0].mlb_player_id).toBeNull();
  });
});

describe("dkMatchReportFromCanonicalPool", () => {
  it("computes dk_entries / matched_to_mlb from the pool's own player count and unmatchedCount", () => {
    const report = dkMatchReportFromCanonicalPool(pool([player({ dkPlayerId: "d1" }), player({ dkPlayerId: "d2" })], { unmatchedCount: 1 }));
    expect(report.dk_entries).toBe(2);
    expect(report.matched_to_mlb).toBe(1);
  });

  it("computes eligibility.starting_pitchers from pitcher rows with STARTING_PITCHER status only", () => {
    const players = [
      player({ dkPlayerId: "p1", playerType: "pitcher", eligibilityStatus: "STARTING_PITCHER" }),
      player({ dkPlayerId: "p2", playerType: "pitcher", eligibilityStatus: "RELIEF_PITCHER" }),
      player({ dkPlayerId: "h1", playerType: "hitter", eligibilityStatus: "STARTING_HITTER" }),
    ];
    const report = dkMatchReportFromCanonicalPool(pool(players));
    expect((report.eligibility as { starting_pitchers: number }).starting_pitchers).toBe(1);
  });

  it("mirrors eligibility.optimizer_eligible from the pool's own activePlayers rollup", () => {
    const players = [player({ dkPlayerId: "d1", optimizerEligible: true }), player({ dkPlayerId: "d2", optimizerEligible: false })];
    const report = dkMatchReportFromCanonicalPool(pool(players));
    expect((report.eligibility as { optimizer_eligible: number }).optimizer_eligible).toBe(1);
  });

  // REGRESSION target: the real dk_match_report_ this replaces drove
  // lib/slateReadiness.ts's "Lineups Confirmed" tile via
  // teams_awaiting_lineups. This must report a REAL team list derived
  // from real eligibility data, never an empty [] that would silently
  // read back as "every team confirmed" the way a missing document does
  // (see slateReadiness.ts's own honest-absence handling for that case).
  it("derives teams_awaiting_lineups literally from hitter eligibilityStatus === LINEUP_UNCONFIRMED", () => {
    const players = [
      player({ dkPlayerId: "h1", team: "BOS", eligibilityStatus: "LINEUP_UNCONFIRMED" }),
      player({ dkPlayerId: "h2", team: "TOR", eligibilityStatus: "STARTING_HITTER" }),
      // A pitcher with LINEUP_UNCONFIRMED must not count -- this field is
      // about HITTER lineup confirmation specifically.
      player({ dkPlayerId: "p1", team: "NYY", playerType: "pitcher", eligibilityStatus: "LINEUP_UNCONFIRMED" }),
    ];
    const report = dkMatchReportFromCanonicalPool(pool(players));
    expect(report.teams_awaiting_lineups).toEqual(["BOS"]);
  });

  it("reports an empty teams_awaiting_lineups array (not fabricated confidence) when every hitter is confirmed", () => {
    const report = dkMatchReportFromCanonicalPool(pool([player({ eligibilityStatus: "STARTING_HITTER" })]));
    expect(report.teams_awaiting_lineups).toEqual([]);
  });

  it("computes salary_coverage_percent from real (non-zero) salaries, not a fixed 100", () => {
    const players = [player({ dkPlayerId: "d1", salary: 4000 }), player({ dkPlayerId: "d2", salary: 0 })];
    const report = dkMatchReportFromCanonicalPool(pool(players));
    expect(report.salary_coverage_percent).toBe(50);
  });

  it("groups dk_game_matches by real gameId for matched players", () => {
    const players = [
      player({ dkPlayerId: "h1", team: "BOS", opponent: "TOR", gameId: "g1" }),
      player({ dkPlayerId: "h2", team: "TOR", opponent: "BOS", gameId: "g1" }),
    ];
    const report = dkMatchReportFromCanonicalPool(pool(players));
    const matches = report.dk_game_matches as Record<string, { status: string; research_game_id: string | null }>;
    expect(Object.keys(matches)).toEqual(["g1"]);
    expect(matches.g1.status).toBe("matched");
    expect(matches.g1.research_game_id).toBe("g1");
  });

  it("groups an unresolved player (gameId null) as not_matched by team pair, deduplicated from both sides", () => {
    const players = [
      player({ dkPlayerId: "h1", team: "BOS", opponent: "TOR", gameId: null }),
      player({ dkPlayerId: "h2", team: "TOR", opponent: "BOS", gameId: null }),
    ];
    const report = dkMatchReportFromCanonicalPool(pool(players));
    const matches = report.dk_game_matches as Record<string, { status: string; research_game_id: string | null }>;
    expect(Object.keys(matches)).toHaveLength(1);
    expect(Object.values(matches)[0].status).toBe("not_matched");
    expect(Object.values(matches)[0].research_game_id).toBeNull();
  });
});

describe("resolveDkBundle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("LEGACY_R2: calls the three original loaders unchanged", async () => {
    const { loadLatestDKPlayerPool, loadLatestDkMatchReport, loadLatestProviderSlate } = await import("../loaders");
    vi.mocked(loadLatestDKPlayerPool).mockResolvedValue({ data: { slate_date: "2026-09-09" } as never, path: "p" });
    vi.mocked(loadLatestDkMatchReport).mockResolvedValue({ data: { dk_entries: 5 }, path: "m" });
    vi.mocked(loadLatestProviderSlate).mockResolvedValue({ data: { generated_at_utc: "2026-09-09T19:00:00Z", provider_name: "draftkings_unofficial_live", is_mock: false }, path: "s" });

    const bundle = await resolveDkBundle("LEGACY_R2", "2026-09-09", "main");
    expect(bundle.pool).toEqual({ slate_date: "2026-09-09" });
    expect(bundle.matchReport).toEqual({ dk_entries: 5 });
    expect(bundle.providerSlate).toEqual({ generated_at_utc: "2026-09-09T19:00:00Z", provider_name: "draftkings_unofficial_live", is_mock: false });
    expect(loadLatestDKPlayerPool).toHaveBeenCalledWith("2026-09-09", "main");
  });

  it("CANONICAL_POSTGRES: returns all-null (never guesses) when no slate is selected", async () => {
    const { canonicalGetSlatePool } = await import("../servingBackend/canonicalPostgresBackend");
    const bundle = await resolveDkBundle("CANONICAL_POSTGRES", "2026-09-09", null);
    expect(bundle).toEqual({ pool: null, matchReport: null, providerSlate: null });
    expect(canonicalGetSlatePool).not.toHaveBeenCalled();
  });

  it("CANONICAL_POSTGRES: converts a real result into all three legacy shapes", async () => {
    const { canonicalGetSlatePool } = await import("../servingBackend/canonicalPostgresBackend");
    vi.mocked(canonicalGetSlatePool).mockResolvedValue(pool([player({ dkPlayerId: "d1" })]));

    const bundle = await resolveDkBundle("CANONICAL_POSTGRES", "2026-09-09", "dkunofficial-153240");
    expect(bundle.pool?.player_count).toBe(1);
    expect((bundle.matchReport as { dk_entries: number }).dk_entries).toBe(1);
    expect(bundle.providerSlate).toEqual({ generated_at_utc: "2026-09-09T19:00:00Z", provider_name: "draftkings_unofficial_live", is_mock: false });
  });

  // REGRESSION target: canonicalGetSlatePool throws for an absent/expired
  // slate (see its own docstring) -- a page must see the same honest
  // "no data" null it already handles everywhere, never a crash.
  it("CANONICAL_POSTGRES: degrades to all-null (never throws) when the slate is absent or expired", async () => {
    const { canonicalGetSlatePool } = await import("../servingBackend/canonicalPostgresBackend");
    vi.mocked(canonicalGetSlatePool).mockRejectedValue(new Error("Canonical slate x not found for 2026-09-09"));

    const bundle = await resolveDkBundle("CANONICAL_POSTGRES", "2026-09-09", "does-not-exist");
    expect(bundle).toEqual({ pool: null, matchReport: null, providerSlate: null });
  });
});
