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

export interface NflUsageInfo {
  rolling: Record<string, number | null>;
  season_to_date: Record<string, number | null>;
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
  matchup: NflMatchupInfo | null;
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
}

export interface NflLineup {
  index: number;
  total_salary: number;
  remaining_salary: number;
  total_projection: number | null;
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

export const NFL_ROSTER_SLOT_ORDER = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"];
export const NFL_POSITIONS = ["QB", "RB", "WR", "TE", "DST"] as const;
export type NflPosition = (typeof NFL_POSITIONS)[number];

// A DraftGroup known to be a real, live NFL Classic slate as of this
// milestone -- used only as the default pre-fill for local review; the
// selector itself always calls the real discovery API, never hardcodes
// this as the only option.
export const DEFAULT_NFL_DRAFT_GROUP_ID = 151307;
