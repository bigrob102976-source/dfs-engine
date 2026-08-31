// Types for Milestone 14's interactive optimizer workspace
// (/dashboard/optimizer). Distinct from lib/orchestrator/'s types --
// that module drives the fixed one-click "Refresh Today's Slate"
// pipeline; this one drives on-demand, user-configured lineup builds
// against a player pool the user is actively browsing/locking/excluding.

import type { AiSignalContribution } from "../aiProjections";
import type { BlueCollarCoverage } from "../blueCollarProjections";
import type { DkSlateVegasCoverage } from "../dkVegasCoverage";
import type { NativeHitterComponents, NativePitcherComponents } from "../nativeProjections";
import type { ProviderSource, SlateOption } from "../orchestrator/types";
import type { Lineup } from "../types";

export type { SlateOption };

// Worker-reliability fix: a real, correctly-provenanced provider-slate
// artifact stays usable well past the 15-minute FRESH window instead of
// triggering a live DraftKings call from Railway (permanently blocked --
// see draftkings_unofficial/README.md). "stale" means real, reused data
// older than 15 minutes but still within the safe reuse ceiling; see
// poolCache.ts's PROVIDER_SLATE_STALE_MAX_MS for the exact bound.
export type ProviderDataStatus = "fresh" | "stale";

export interface SlateListResult {
  // "stale_expired": a real provider-slate artifact exists for this date
  // but has aged past the safe reuse ceiling -- the artifact is NOT
  // reused (its slate/salary data is too old to trust) and no live
  // DraftKings call is attempted (that path is known to fail from
  // Railway). Distinct from "unavailable" so the UI can explain the
  // real cause (the worker has fallen behind) rather than a generic
  // provider failure.
  status: "ready" | "not_connected" | "unavailable" | "auth_failed" | "no_slate" | "stale_expired";
  reason: string | null;
  providerName: string | null;
  providerType: "mock" | "real" | null;
  isMock: boolean;
  isConnected: boolean;
  source: ProviderSource | null;
  slates: SlateOption[];
  slatesAvailable: number;
  // null when status !== "ready" (nothing meaningful to call fresh/stale).
  dataStatus: ProviderDataStatus | null;
  artifactAgeSeconds: number | null;
  lastUpdatedAt: string | null;
}

/** One row in the player-pool table -- a flattened, UI-friendly view of
 * a DFSPlayer (dfs/models.py) plus whatever ownership projection could
 * be joined in. Never invents a value: any field the pipeline hasn't
 * produced yet (no projection, no ownership) stays null. */
export interface PoolPlayerRow {
  dkPlayerId: string;
  mlbPlayerId: string | null;
  name: string;
  team: string;
  opponent: string | null;
  gameId: string | null;
  playerType: "pitcher" | "hitter";
  positions: string[];
  battingOrder: number | null;
  salary: number;
  projection: number | null;
  ceiling: number | null;
  value: number | null; // projection per $1,000 salary
  ownership: number | null;
  leverage: number | null;
  risk: number | null;
  confidence: number | null;
  lineupStatus: string;
  matchStatus: string;
  // Milestone 30.1: the explicit playing-status/optimizer-eligibility
  // layer (dfs/eligibility.py) -- STARTING_PITCHER | STARTING_HITTER |
  // LINEUP_UNCONFIRMED | BENCH | RELIEF_PITCHER | SCRATCHED | UNMATCHED |
  // AMBIGUOUS. null/false for pools saved before this milestone.
  eligibilityStatus: string | null;
  optimizerEligible: boolean;

  // Milestone 17: optional three-way projection comparison, joined in
  // from the latest adjusted-projection snapshot by mlbPlayerId. `projection`
  // above is ALWAYS the independent (Big Money) value, unaffected by any
  // of these -- see lib/externalProjections.ts.
  externalProjection: number | null;
  adjustedProjection: number | null;
  adjustmentDelta: number | null;
  adjustmentPercent: number | null;
  adjustmentReasons: string[];

  // Milestone 20: AI Projection Engine -- joined in from the latest
  // ai_projection_*.json snapshot by mlbPlayerId. `projection` above is
  // still ALWAYS the independent value; see lib/aiProjections.ts.
  aiProjection: number | null;
  aiCeiling: number | null;
  aiFloor: number | null;
  aiDelta: number | null; // aiProjection - projection (independent)
  aiConfidence: number | null;
  aiRisk: number | null;
  aiGrade: string | null;
  aiValueScore: number | null;
  aiSignals: AiSignalContribution[];
  aiReasons: string[];
  aiSummary: string | null;

  // Milestone 23: Native Projection Model -- joined in from the latest
  // native_projection_*.json snapshot by mlbPlayerId. `projection` above
  // is still ALWAYS the independent value; see lib/nativeProjections.ts.
  nativeProjection: number | null;
  nativeCeiling: number | null;
  nativeFloor: number | null;
  nativeDelta: number | null; // nativeProjection - projection (independent)
  nativeConfidence: number | null;
  nativeReasons: string[];
  nativeExpectedPa: number | null; // hitters only
  nativeExpectedInnings: number | null; // pitchers only
  nativeHitterComponents: NativeHitterComponents | null;
  nativePitcherComponents: NativePitcherComponents | null;

  // FantasyPros: a COMPARISON + OPTIONAL OPTIMIZER SOURCE only -- joined
  // in from the latest fantasypros_snapshots/<date>/*.json snapshot by
  // mlbPlayerId, same shape as native/AI above. `projection` above is
  // still ALWAYS the independent value; never fed into Native/AI's own
  // computation (see lib/fantasyProsProjections.ts's module docstring).
  fantasyProsProjection: number | null;
  fantasyProsMatchStatus: "matched" | "unmatched" | "ambiguous" | null;

  // Milestone 32.2B/32.3B: Big Money ML -- comparison column, joined in
  // from the unified (pitcher + hitter) ml_projection_snapshots/<date>/
  // *.json snapshot streams by mlbPlayerId (see lib/mlProjections.ts's
  // getMlProjectionByPlayerId). Starters only. `projection` above is
  // still ALWAYS the independent value.
  //
  // Milestone 32.4: "big_money_ml" IS now a selectable ProjectionSource
  // (see below) -- but ADMIN/OWNER-only, gated by the
  // 'mlb.big_money_ml_optimizer' feature flag (default ADMIN_ONLY, see
  // lib/entitlements/featureVisibility.ts) both in the UI selector
  // (OptimizerWorkspace.tsx) AND server-side in the build API route
  // (never trust client-side hiding alone). When selected,
  // writeProjectionOverridesFile's "big_money_ml" branch AND
  // scripts/optimize_dk_lineups.py's --strict-projection-source flag
  // together enforce NO FALLBACK to another source for a player missing
  // an ML projection -- they are excluded from the build entirely
  // rather than silently reverting to native/ai/independent.
  mlProjection: number | null;
  mlDataQualityScore: number | null;
  mlProjectionStatus: "LIVE_PREGAME" | "PREGAME_FROZEN" | "MISSING" | "INVALID_FEATURE_PARITY" | null;
  mlFeatureTimestamp: string | null;

  // BlueCollar DFS: a COMPARISON + OPTIONAL ADMIN-ONLY OPTIMIZER SOURCE
  // only -- joined in from the latest, slate-scoped
  // bluecollar_projection_snapshots/<date>/<slateId>/*.json snapshot by
  // mlbPlayerId (see lib/blueCollarProjections.ts). `projection` above
  // is still ALWAYS the independent value; never fed into Native/AI/ML's
  // own computation.
  //
  // ZERO-VALUE RULE: blueCollarProjection is null whenever BlueCollar
  // reported no genuinely usable projection (a raw value <= 0 is treated
  // as NOT AVAILABLE, never a real zero -- see bluecollar/build.py).
  // blueCollarRawProjection preserves the raw value regardless, for
  // debugging only -- UI code must never show it to a member as "the"
  // projection.
  blueCollarProjection: number | null;
  blueCollarRawProjection: number | null;
  blueCollarMatchStatus: "matched" | "unmatched" | "ambiguous" | null;
}

export type ProjectionSource = "independent" | "external" | "adjusted" | "ai" | "native" | "fantasypros" | "big_money_ml" | "bluecollar";

export interface OptimizerPoolResult {
  date: string;
  slateId: string;
  slateName: string | null;
  providerName: string | null;
  isMock: boolean;
  providerSource: ProviderSource | null;
  generatedAt: string;
  players: PoolPlayerRow[];
  activePlayers: number;
  pitcherCount: number;
  hitterCount: number;
  confirmedLineupGames: number;
  unconfirmedLineupGames: number;
  unmatchedCount: number;
  slateGames: number;
  rosterFeasibilityPass: boolean;
  salaryCap: number;
  hasOwnership: boolean;
  hasExternalProjections: boolean;
  // Milestone 27: the active external baseline's real provider_name
  // (e.g. "BlueCollar DFS"), or null when none is loaded -- lets the UI
  // label this slot honestly (BLUECOLLAR vs a generic external source)
  // instead of a bare "External."
  externalProviderName: string | null;
  hasAiProjections: boolean;
  hasNativeProjections: boolean;
  hasFantasyProsProjections: boolean;
  hasMlProjections: boolean;
  hasBlueCollarProjections: boolean;
  // BlueCollar's own matched slate name/status for THIS DK slate (e.g.
  // "1:35PM ET Main 8 Games" / "matched"), or null when no BlueCollar
  // snapshot exists yet -- lets the UI show "BLUECOLLAR NOT UPDATED"
  // honestly instead of silently showing nothing.
  blueCollarSlateName: string | null;
  blueCollarSlateMatchStatus: string | null;
  blueCollarUpdated: string | null;
  // M32.7: BlueCollar's own funnel, as separate counts (never collapsed
  // into one "coverage %") -- see lib/blueCollarProjections.ts's
  // computeBlueCollarCoverage, the single source of truth for this.
  blueCollarCoverage: BlueCollarCoverage;
  vegasCoverage: DkSlateVegasCoverage;
  // Worker-reliability fix: whether the underlying DraftKings artifact
  // this pool was built from is fresh (<=15 min old) or a reused,
  // still-real stale artifact -- see poolCache.ts. Never "expired": an
  // expired artifact is refused before a pool is ever built (loadPool
  // throws instead).
  dataStatus: ProviderDataStatus;
  artifactAgeSeconds: number;
  lastUpdatedAt: string;
}

export interface OptimizerBuildRequest {
  date: string;
  slateId: string;
  lineups: number;
  objective: "projection" | "ceiling" | "balanced" | "leverage";
  locks: string[]; // player names
  exclusions: string[]; // player names
  maxExposure: Record<string, number>; // player name -> fraction (0-1)
  stackSize: number | null;
  stackTeam: string | null;
  allowPitcherVsHitter: boolean;
  minSalary: number | null;
  minUnique: number;
  minConfidence: number | null;
  maxPlayerRisk: number | null;
  projectionSource: ProjectionSource;
}

/** Milestone 32.6 Part 2/3: how much of the pool actually made it into
 * the solver's eligible-player list, and why the rest didn't -- mirrors
 * scripts/optimize_dk_lineups.py::_coverage_summary() exactly. Powers
 * both the "Coverage: X/Y eligible players" indicator (Part 3) and the
 * Stage/Reason diagnostics that now precede the generic per-position
 * roster-shortfall messages in `errors` (Part 2) when the pool shrank
 * because of missing projections rather than a genuine roster/salary/
 * stack conflict. `null` only when validation never reached the point
 * of building a player list at all (e.g. "no pool loaded for this slate"). */
export interface OptimizerCoverageSummary {
  poolSize: number;
  optimizerEligible: number;
  usableForBuild: number;
  skippedMissingProjection: number;
  excludedMissingSource: number;
  projectionSource: ProjectionSource;
  strictSource: boolean;
}

export interface OptimizerValidationResult {
  errors: string[];
  coverage: OptimizerCoverageSummary | null;
}

export interface OptimizerBuildResult {
  ok: boolean;
  errors: string[];
  coverage: OptimizerCoverageSummary | null;
  lineupSetPath: string | null;
  csvPath: string | null;
  lineupsRequested: number;
  lineupsGenerated: number;
  stoppedReason: string | null;
  lineups: Lineup[];
  elapsedMs: number;
  // Milestone 32.4 -- surfaced straight from the persisted lineup set so
  // the UI can show "N players excluded (no ML projection)" immediately
  // after a strict-source build without a second fetch.
  excludedMissingProjectionSource: string[];
}

export interface ExposureRow {
  name: string;
  team: string;
  playerType: "pitcher" | "hitter";
  lineups: number;
  exposurePercent: number;
}

export interface StackExposureRow {
  team: string;
  lineups: number;
  exposurePercent: number;
}
