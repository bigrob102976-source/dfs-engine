import { loadLatestDKPlayerPool, loadLatestDkMatchReport, loadLatestProviderSlate } from "./loaders";
import type { OptimizerPoolResult, PoolPlayerRow } from "./optimizerWorkspace/types";
import { canonicalGetSlatePool } from "./servingBackend/canonicalPostgresBackend";
import type { ServingBackendKind } from "./servingBackend/types";
import type { DFSPlayer, DKPlayerPool } from "./types";

// The dashboard's DK-dependent tiles (Vegas Coverage, DK Players,
// Identity Resolved, Starting Pitchers, Team Readiness, Lineups
// Confirmed) were built against three legacy dfs_input/ artifacts --
// dk_player_pool_<ts>.json, dk_match_report_<ts>.json, and
// provider_slate_<ts>.json -- written by
// scripts/build_dfs_pool_from_provider.py. That script was superseded
// when eligibility/projections/ownership moved into canonical Postgres
// (dfs/eligibility.py's real output, bridged by
// lib/servingBackend/canonicalPostgresBackend.ts) and was never added
// back into the automated refresh chain -- confirmed empty in
// production object storage for dk_player_pool_/dk_match_report_ going
// back to at least 2026-09-06, while provider_slate_ (a DIFFERENT
// artifact, still written by the separate DK-fetch worker stage) keeps
// landing normally. This module is the read-shape translation from what
// canonicalGetSlatePool already computes (real, persisted data -- never
// invented here) into the three legacy shapes the page/lib/normalize.ts
// and lib/slateReadiness.ts already know how to render, so member pages
// serve canonical without duplicating any computation.
//
// LEGACY_R2 stays on the original loaders (lib/loaders.ts) unchanged --
// this module is CANONICAL_POSTGRES-only.

/** PoolPlayerRow -> DFSPlayer. Every field DFSPlayer declares that
 * PoolPlayerRow simply doesn't carry (tags, reasons, overall_score,
 * season_sample_size, floor) is left honestly null/empty rather than
 * invented -- canonical's own projection bridge (MLB FINISH MODE Phase
 * B/D) doesn't compute a separate floor value on the pool row today, and
 * tags/reasons are an AI-agent-authored field this backend never
 * populates (see canonicalPostgresBackend.ts's own module docstring:
 * AI/FantasyPros/BlueCollar/ML stay intentionally absent). */
function dfsPlayerFromPoolRow(p: PoolPlayerRow): DFSPlayer {
  return {
    dk_player_id: p.dkPlayerId,
    name: p.name,
    team: p.team,
    player_type: p.playerType,
    dk_positions: p.positions,
    salary: p.salary,
    mlb_player_id: p.mlbPlayerId,
    opponent: p.opponent,
    game_id: p.gameId,
    batting_order: p.battingOrder,
    projection: p.projection,
    ceiling: p.ceiling,
    floor: null,
    overall_score: null,
    risk_score: p.risk,
    confidence: p.confidence,
    tags: [],
    reasons: [],
    season_sample_size: null,
    lineup_status: p.lineupStatus,
    match_status: p.matchStatus,
    eligibility_status: p.eligibilityStatus ?? undefined,
    optimizer_eligible: p.optimizerEligible,
    lineup_confirmation: p.lineupConfirmation ?? null,
    probable_confidence: p.probableConfidence ?? null,
    probable_reason: p.probableReason ?? null,
    projected_batting_order: p.projectedBattingOrder ?? null,
  };
}

/** canonicalGetSlatePool's OptimizerPoolResult -> the DKPlayerPool shape
 * buildHitterRows/buildPitcherRows (lib/normalize.ts) already expect --
 * the same shape lib/loaders.ts::loadLatestDKPlayerPool returns for
 * LEGACY_R2. Once this is wired into a page, every downstream join
 * (ownership, ML/BlueCollar comparison columns, Team Readiness's
 * eligibilityStatus read) works unchanged, because normalize.ts only
 * ever reads the DKPlayerPool/DFSPlayer shape, never the backend that
 * produced it. */
export function dkPlayerPoolFromCanonicalPool(result: OptimizerPoolResult): DKPlayerPool {
  return {
    slate_date: result.date,
    generated_at_utc: result.lastUpdatedAt,
    pitcher_snapshot_path: null,
    batter_snapshot_path: null,
    roster_feasibility_pass: result.rosterFeasibilityPass,
    player_count: result.players.length,
    players: result.players.map(dfsPlayerFromPoolRow),
    selected_slate_id: result.slateId,
  };
}

/** A dk_match_report_<ts>.json-shaped document synthesized from the same
 * OptimizerPoolResult, for the two callers that read the real match
 * report directly (lib/slateReadiness.ts::buildSlateReadinessSummary,
 * lib/dkVegasCoverage.ts::buildDkSlateVegasCoverage) -- both already
 * treat a null matchReport as "no data available" (never fabricating a
 * count from its absence, see slateReadiness.ts's own honest-absence
 * handling), so a page only needs to pass this in place of the dead
 * loadLatestDkMatchReport() result.
 *
 * teams_awaiting_lineups is derived literally from
 * eligibilityStatus === "LINEUP_UNCONFIRMED" among HITTER rows (the same
 * signal the real dk_match_report used to report from
 * dfs/slate_validation.py). This is NOT identical to "every team with no
 * CONFIRMED starting hitter" (lib/slateReadiness.ts::buildTeamReadinessRows
 * uses that broader definition for its own per-team CONFIRMED/UNCONFIRMED
 * badge) -- a team whose hitters are all BENCH/UNMATCHED rather than
 * explicitly LINEUP_UNCONFIRMED would not appear here. Kept narrow and
 * literal on purpose so this function's output stays a faithful mirror
 * of the field name it's replacing, not a reinterpretation of it. */
export function dkMatchReportFromCanonicalPool(result: OptimizerPoolResult): Record<string, unknown> {
  const dkEntries = result.players.length;
  const matchedToMlb = dkEntries - result.unmatchedCount;
  const startingPitchers = result.players.filter((p) => p.playerType === "pitcher" && p.eligibilityStatus === "STARTING_PITCHER").length;
  const withSalary = result.players.filter((p) => p.salary > 0).length;

  const teamsAwaiting = new Set<string>();
  for (const p of result.players) {
    if (p.playerType === "hitter" && p.eligibilityStatus === "LINEUP_UNCONFIRMED") teamsAwaiting.add(p.team);
  }

  return {
    dk_entries: dkEntries,
    matched_to_mlb: matchedToMlb,
    eligibility: {
      starting_pitchers: startingPitchers,
      optimizer_eligible: result.activePlayers,
    },
    teams_awaiting_lineups: Array.from(teamsAwaiting),
    salary_coverage_percent: dkEntries > 0 ? Math.round((100 * withSalary) / dkEntries * 10) / 10 : 0,
    dk_game_matches: dkGameMatchesFromCanonicalPool(result),
  };
}

/** Reconstructs a dk_game_matches-shaped map (lib/dkVegasCoverage.ts's
 * only real input) by grouping pool rows by their already-resolved
 * gameId. PoolPlayerRow.gameId is the SAME real-MLB-game identity
 * SlateOption.gameIds and every game_environment_snapshots/ row use
 * (both ultimately resolved by the same research-game matching dfs/
 * eligibility.py performs at promotion/eligibility-compute time -- see
 * canonicalPostgresBackend.ts's own docstring) -- never DK's own raw
 * "gameInfo" descriptor string, which canonical's schema doesn't carry
 * at all. A player with gameId === null (identity/eligibility not yet
 * resolved to a real game) is grouped as NOT_MATCHED by (team, opponent)
 * instead, so an unresolved player still surfaces as a real, honestly-
 * unmatched row rather than silently vanishing from the coverage count.
 * away/home ordering for the two synthesized label fields is arbitrary
 * (canonical doesn't record which side DK calls "away") -- harmless here
 * since buildDkSlateVegasCoverage always prefers the environment
 * report's own away_team/home_team for its primary matchupLabel once a
 * game is matched; these two fields are the NOT_MATCHED-only fallback
 * label and the two coverage-detail columns. */
function dkGameMatchesFromCanonicalPool(result: OptimizerPoolResult): Record<string, { status: string; research_game_id: string | null; dk_away: string | null; dk_home: string | null }> {
  const matched = new Map<string, { away: string; home: string }>();
  const unmatchedPairKeys = new Set<string>();
  const unmatched = new Map<string, { away: string; home: string }>();

  for (const p of result.players) {
    if (!p.team || !p.opponent) continue;
    if (p.gameId) {
      if (!matched.has(p.gameId)) matched.set(p.gameId, { away: p.team, home: p.opponent });
      continue;
    }
    const pairKey = [p.team, p.opponent].sort().join("@");
    if (unmatchedPairKeys.has(pairKey)) continue;
    unmatchedPairKeys.add(pairKey);
    unmatched.set(`unmatched:${pairKey}`, { away: p.team, home: p.opponent });
  }

  const out: Record<string, { status: string; research_game_id: string | null; dk_away: string | null; dk_home: string | null }> = {};
  for (const [gameId, { away, home }] of matched) {
    out[gameId] = { status: "matched", research_game_id: gameId, dk_away: away, dk_home: home };
  }
  for (const [key, { away, home }] of unmatched) {
    out[key] = { status: "not_matched", research_game_id: null, dk_away: away, dk_home: home };
  }
  return out;
}

export interface DkBundle {
  pool: DKPlayerPool | null;
  matchReport: Record<string, unknown> | null;
  /** Only the 3 raw fields any current page reads off provider_slate_
   * (generated_at_utc/provider_name/is_mock) -- not the full legacy
   * document shape, which has no canonical equivalent (canonical never
   * writes a provider_slate_-style artifact at all; these three values
   * already exist directly on OptimizerPoolResult). */
  providerSlate: { generated_at_utc: string | null; provider_name: string | null; is_mock: boolean } | null;
}

/** The single call site a page uses instead of loadLatestDKPlayerPool +
 * loadLatestDkMatchReport + loadLatestProviderSlate. LEGACY_R2 keeps
 * calling those three loaders completely unchanged. CANONICAL_POSTGRES
 * calls canonicalGetSlatePool() once and converts its one result into
 * all three legacy shapes via this module's translators above.
 *
 * No slate selected (`slateId` null) under canonical returns all three
 * as null (the existing "no slate selected" UI states already handle
 * this everywhere) rather than guessing -- unlike legacy's
 * loadLatestDKPlayerPool(date, undefined), which falls back to
 * "whichever pool file was built most recently" (see that function's own
 * docstring), canonical has no per-slate-row concept of "most recent
 * build" to fall back to, so a real slate id is required. Command
 * Center's own resolveSlateContext(..., { autoSelectSoleSlate: true })
 * already avoids this in the common single-slate case. A missing/
 * expired canonical slate (canonicalGetSlatePool throws -- see its own
 * docstring) degrades the same way: all three null, same as legacy's
 * honest-absence states, never a thrown error reaching the page. */
export async function resolveDkBundle(backendKind: ServingBackendKind, date: string, slateId: string | null): Promise<DkBundle> {
  if (backendKind === "LEGACY_R2") {
    const [poolLoaded, matchReportLoaded, providerSlateLoaded] = await Promise.all([
      loadLatestDKPlayerPool(date, slateId),
      loadLatestDkMatchReport(date, slateId),
      loadLatestProviderSlate(date),
    ]);
    const providerSlateDoc = providerSlateLoaded.data;
    return {
      pool: poolLoaded.data,
      matchReport: matchReportLoaded.data,
      providerSlate: providerSlateDoc
        ? {
            generated_at_utc: typeof providerSlateDoc.generated_at_utc === "string" ? providerSlateDoc.generated_at_utc : null,
            provider_name: typeof providerSlateDoc.provider_name === "string" ? providerSlateDoc.provider_name : null,
            is_mock: Boolean(providerSlateDoc.is_mock),
          }
        : null,
    };
  }

  if (!slateId) return { pool: null, matchReport: null, providerSlate: null };

  try {
    const result = await canonicalGetSlatePool(date, slateId);
    return {
      pool: dkPlayerPoolFromCanonicalPool(result),
      matchReport: dkMatchReportFromCanonicalPool(result),
      providerSlate: { generated_at_utc: result.lastUpdatedAt, provider_name: result.providerName, is_mock: result.isMock },
    };
  } catch {
    // Absent/expired canonical slate -- honest "no data" (same as every
    // other loader's null-on-absence contract), never surfaced as a
    // page-crashing error for what is, from a member's perspective, the
    // same "nothing to show yet" state legacy already renders.
    return { pool: null, matchReport: null, providerSlate: null };
  }
}
