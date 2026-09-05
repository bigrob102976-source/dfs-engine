// NFL UI M1 -- shared types mirroring scripts/nfl_dashboard_data.py's
// and scripts/nfl_dashboard_optimize.py's real JSON output shapes.
// Every optional/nullable field here reflects a REAL "not available"
// state from the backend (missing Vegas credentials, unresolved
// identity, no trained model) -- never invented to make a type happy.

export interface NflGameRow {
  game_id: string;
  game_description: string | null;
  game_start_time: string | null;
  spread_home: number | null;
  total: number | null;
  home_implied_total: number | null;
  away_implied_total: number | null;
  lock: NflGameLockInfo | null;
}

export interface NflProjectionInfo {
  projection: number | null;
  floor: number | null;
  ceiling: number | null;
  source: string;
  model_name: string | null;
  model_version: string | null;
}

export interface NflMatchupInfo {
  spread_home: number | null;
  total: number | null;
  home_implied_total: number | null;
  away_implied_total: number | null;
}

// NFL M12 -- Big Money Native ownership (nfl_ownership_v1). A
// deterministic estimator, never a trained ML model -- see method
// below, which is always "deterministic_estimator" until real
// historical DK ownership exists to train against. null (not 0)
// whenever the player has no usable projection to estimate from.
export interface NflOwnershipInfo {
  ownership_projection: number | null;
  ownership_rank: number | null;
  ownership_tier: string | null;
  chalk_score: number | null;
  leverage_score: number | null;
  ownership_confidence: number | null;
  value: number | null;
  flex_ownership_component: number | null;
  source: string;
  method: string;
  model_version: string;
}

export interface NflOwnershipCoverage {
  total: number;
  generated: number;
}

export interface NflUsageInfo {
  rolling: Record<string, number | null>;
  season_to_date: Record<string, number | null>;
}

// NFL M14 -- real, normalized player status (nfl/status.py). Never a
// fabricated "Active" badge -- UNKNOWN means DK returned a raw status
// string this project hasn't seen before, not "assumed healthy".
export type NflNormalizedStatus = "ACTIVE" | "QUESTIONABLE" | "DOUBTFUL" | "OUT" | "INACTIVE" | "IR" | "UNKNOWN";

export interface NflStatusInfo {
  normalized_status: NflNormalizedStatus;
  raw_status: string | null;
  excluded_by_default: boolean;
  warn: boolean;
}

// NFL M14 -- real per-game lock state (nfl/game_lock.py), computed from
// DraftKings' own real game_start_time. null only when DK hasn't
// published a start time for this game yet.
export interface NflGameLockInfo {
  game_id: string;
  start_time_utc: string;
  start_time_eastern: string;
  home_team: string | null;
  away_team: string | null;
  lock_state: "PRELOCK" | "LOCKED";
  locked: boolean;
}

export interface NflPlayerRow {
  draftkings_player_id: string;
  name: string;
  position: string;
  team: string;
  opponent: string | null;
  game_id: string;
  salary: number;
  roster_slots: string[];
  is_team_entity: boolean;
  status: string | null;
  injury_status: string | null;
  gsis_id: string | null;
  identity_resolved: boolean;
  usage: NflUsageInfo | null;
  projection: NflProjectionInfo | null;
  ownership: NflOwnershipInfo | null;
  matchup: NflMatchupInfo | null;
  status_info: NflStatusInfo;
  game_lock: NflGameLockInfo | null;
}

export interface NflPositionCoverage {
  total: number;
  projected: number;
}

export interface NflSlateData {
  draft_group_id: number;
  slate_date: string;
  slate_name: string | null;
  source_provenance: string;
  salary_cap: number;
  current_season: number;
  current_week: number;
  prior_season: number;
  current_completed_weeks: number[];
  games: NflGameRow[];
  game_count: number;
  player_count: number;
  position_counts: Record<string, number>;
  identity: { total: number; resolved: number; unresolved: number };
  projection_coverage: Record<string, NflPositionCoverage>;
  projection_error: string | null;
  ownership_coverage: Record<string, NflOwnershipCoverage>;
  ownership_generated: number;
  ownership_missing: number;
  ownership_normalization: Record<string, unknown> | null;
  ownership_model_version: string | null;
  vegas_configured: boolean;
  vegas_source_provenance: string;
  players: NflPlayerRow[];
  error?: string;
}

export interface NflLineupAssignment {
  slot: string;
  draftkings_player_id: string;
  name: string;
  position: string;
  team: string;
  salary: number;
  // NFL M12 -- null whenever Big Money Native has no ownership estimate
  // for this player (or the lineup was generated in "roster_feasibility"
  // mode, which doesn't fetch projections/ownership at all).
  projected_ownership: number | null;
  // NFL M13 -- null unless a real ceiling was available for this player.
  ceiling: number | null;
}

export interface NflLineup {
  index: number;
  total_salary: number;
  remaining_salary: number;
  total_projection: number | null;
  // NFL M13 -- each null unless EVERY assigned player had the real data
  // needed (never a partial/fabricated sum) -- see nfl/optimizer_models.py.
  total_ceiling: number | null;
  sum_ownership: number | null;
  average_ownership: number | null;
  total_leverage_score: number | null;
  qb_stack_team: string | null;
  qb_stack_receiver_count: number;
  bring_back_player: string | null;
  rb_dst_team: string | null;
  assignments: NflLineupAssignment[];
}

export interface NflOptimizeResult {
  requested: number;
  generated: number;
  stopped_reason: string | null;
  mode: string;
  lineups: NflLineup[];
  error?: string;
  error_type?: string;
}

// NFL M13 -- mirrors nfl/optimizer_models.py::NflStackConfig exactly
// (camelCase here, snake_case there -- dashboard/app/api/nfl/optimize/
// route.ts and scripts/nfl_dashboard_optimize.py do the translation).
export type NflQbStackMode = "off" | "single" | "double";
export type NflBringBackMode = "off" | "one";

export interface NflStackConfig {
  qbStackMode: NflQbStackMode;
  bringBackMode: NflBringBackMode;
  rbDstEnabled: boolean;
  maxPlayersPerTeam: number | null;
  maxPlayersPerGame: number | null;
}

export const DEFAULT_NFL_STACK_CONFIG: NflStackConfig = {
  qbStackMode: "off", bringBackMode: "off", rbDstEnabled: false, maxPlayersPerTeam: null, maxPlayersPerGame: null,
};

export type NflObjectiveMode = "roster_feasibility" | "projection" | "ceiling" | "leverage";

export const NFL_ROSTER_SLOT_ORDER = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"];
export const NFL_POSITIONS = ["QB", "RB", "WR", "TE", "DST"] as const;
export type NflPosition = (typeof NFL_POSITIONS)[number];

// A DraftGroup known to be a real, live NFL Classic slate as of this
// milestone -- used only as the default pre-fill for local review; the
// selector itself always calls the real discovery API, never hardcodes
// this as the only option.
export const DEFAULT_NFL_DRAFT_GROUP_ID = 151307;

// ---------------------------------------------------------------------------
// NFL M14 -- saved lineups / late swap / export
// ---------------------------------------------------------------------------

// Mirrors nfl/saved_lineup_models.py::NflSavedLineupSlot exactly.
export interface NflSavedLineupSlot {
  roster_slot: string;
  draftkings_player_id: string;
  name: string;
  team: string;
  opponent: string | null;
  game_id: string;
  game_start_utc: string | null;
  position: string;
  salary: number;
  projection_snapshot: number | null;
  ceiling_snapshot: number | null;
  ownership_snapshot: number | null;
}

export interface NflSavedLineup {
  id: string;
  draft_group_id: number;
  slate_date: string;
  mode: string;
  stack_config: Partial<NflStackConfig>;
  slots: NflSavedLineupSlot[];
  created_at: string;
  updated_at: string;
}

export interface NflLateSwapAssignment extends NflLineupAssignment {
  locked: boolean;
}

export interface NflLateSwapLineup {
  total_salary: number;
  remaining_salary: number;
  total_projection: number | null;
  total_ceiling: number | null;
  sum_ownership: number | null;
  average_ownership: number | null;
  total_leverage_score: number | null;
  qb_stack_team: string | null;
  qb_stack_receiver_count: number;
  bring_back_player: string | null;
  rb_dst_team: string | null;
  assignments: NflLateSwapAssignment[];
}

export interface NflLateSwapResult {
  locked_slots: string[];
  unlocked_slots: string[];
  changed_player_keys: string[];
  fully_locked: boolean;
  error: string | null;
  lineup: NflLateSwapLineup | null;
  error_type?: string;
}
