// Types for Milestone 14's interactive optimizer workspace
// (/dashboard/optimizer). Distinct from lib/orchestrator/'s types --
// that module drives the fixed one-click "Refresh Today's Slate"
// pipeline; this one drives on-demand, user-configured lineup builds
// against a player pool the user is actively browsing/locking/excluding.

import type { SlateOption } from "../orchestrator/types";
import type { Lineup } from "../types";

export type { SlateOption };

export interface SlateListResult {
  status: "ready" | "not_connected" | "unavailable" | "auth_failed" | "no_slate";
  reason: string | null;
  providerName: string | null;
  providerType: "mock" | "real" | null;
  isMock: boolean;
  isConnected: boolean;
  source: "explicit" | "automatic_fallback" | null;
  slates: SlateOption[];
  slatesAvailable: number;
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

  // Milestone 17: optional three-way projection comparison, joined in
  // from the latest adjusted-projection snapshot by mlbPlayerId. `projection`
  // above is ALWAYS the independent (Big Money) value, unaffected by any
  // of these -- see lib/externalProjections.ts.
  externalProjection: number | null;
  adjustedProjection: number | null;
  adjustmentDelta: number | null;
  adjustmentPercent: number | null;
  adjustmentReasons: string[];
}

export type ProjectionSource = "independent" | "external" | "adjusted";

export interface OptimizerPoolResult {
  date: string;
  slateId: string;
  slateName: string | null;
  providerName: string | null;
  isMock: boolean;
  providerSource: "explicit" | "automatic_fallback" | null;
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

export interface OptimizerBuildResult {
  ok: boolean;
  errors: string[];
  lineupSetPath: string | null;
  csvPath: string | null;
  lineupsRequested: number;
  lineupsGenerated: number;
  stoppedReason: string | null;
  lineups: Lineup[];
  elapsedMs: number;
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
