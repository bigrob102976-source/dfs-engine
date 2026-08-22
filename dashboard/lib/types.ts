// Loose TypeScript mirrors of the JSON artifacts produced by the Python
// pipeline (models/, dfs/, ownership/, optimizer/, evaluation/). Only
// fields the dashboard actually reads are typed precisely; deeply nested
// blobs (season_metrics, feature_breakdown, etc.) stay as generic records
// since this is a read-only viewer, not a re-implementation of the models.

export type JsonRecord = Record<string, unknown>;

export interface TimestampFields {
  generated_at?: string;
  generated_at_utc?: string;
  generated_at_local?: string;
  timezone?: string;
}

// ---------------------------------------------------------------------------
// Research package
// ---------------------------------------------------------------------------

export interface SlateIndex extends JsonRecord {
  slate_date: string;
  game_ids: string[];
  team_ids: string[];
  counts: { games: number; teams: number; pitchers: number; batters: number };
  notes: string[];
}

export interface ResearchGame extends JsonRecord {
  game_id: string;
  date: string;
  game_datetime_utc: string | null;
  status: string;
  home_team_abbr: string;
  away_team_abbr: string;
  venue_name: string | null;
  home_probable_pitcher_id: string | null;
  away_probable_pitcher_id: string | null;
  game_number: number | null;
}

// ---------------------------------------------------------------------------
// Pitcher / Batter prediction snapshots
// ---------------------------------------------------------------------------

export interface PitcherRecord extends JsonRecord {
  player_id: string;
  name: string;
  team: string;
  opponent: string;
  game_id?: string;
  venue?: string | null;
  projection: number;
  ceiling: number;
  floor?: number;
  overall_score: number;
  strikeout_score?: number;
  run_prevention_score?: number;
  matchup_score?: number;
  workload_score?: number;
  contact_score?: number;
  risk_score: number;
  confidence: number;
  salary?: number | null;
  tags: string[];
  reasons: string[];
  season_metrics?: JsonRecord;
  recent_metrics?: JsonRecord;
  trend_metrics?: JsonRecord;
  opponent_metrics?: JsonRecord;
}

export interface PitcherSnapshot extends TimestampFields, JsonRecord {
  slate_date: string;
  model_version: string;
  research_package_version?: string;
  pitcher_count: number;
  pitchers: PitcherRecord[];
  research_quality_report?: JsonRecord;
}

export interface BatterRecord extends JsonRecord {
  player_id: string;
  name: string;
  team: string;
  opponent: string;
  game_id?: string;
  venue?: string | null;
  batting_order: number | null;
  position?: string | null;
  batting_hand?: string | null;
  projection: number;
  ceiling: number;
  floor?: number;
  overall_score: number;
  power_score?: number;
  contact_score?: number;
  matchup_score?: number;
  recent_trend_score?: number;
  lineup_position_score?: number;
  risk_score: number;
  confidence: number;
  salary?: number | null;
  tags: string[];
  reasons: string[];
  season_metrics?: JsonRecord;
  recent_metrics?: JsonRecord;
  vs_rhp?: JsonRecord;
  vs_lhp?: JsonRecord;
  opposing_pitcher?: JsonRecord;
  trend_metrics?: JsonRecord;
}

export interface BatterSnapshot extends TimestampFields, JsonRecord {
  slate_date: string;
  model_version: string;
  research_package_version?: string;
  hitter_count: number;
  missing_lineup_game_ids: string[];
  hitters: BatterRecord[];
  research_quality_report?: JsonRecord;
}

// ---------------------------------------------------------------------------
// Ownership snapshot
// ---------------------------------------------------------------------------

export interface OwnershipPlayer extends JsonRecord {
  dk_player_id: string;
  mlb_player_id: string | null;
  name: string;
  team: string;
  opponent: string | null;
  player_type: "pitcher" | "hitter";
  dk_positions: string[];
  salary: number;
  projection: number;
  ceiling: number;
  overall_score: number | null;
  risk_score: number | null;
  confidence: number | null;
  projected_ownership: number;
  ownership_confidence: number;
  chalk_score: number;
  leverage_score: number;
  ownership_tier: string;
  batting_order: number | null;
  feature_breakdown: JsonRecord;
  reasons: string[];
  tags: string[];
  model_version: string;
}

export interface TeamPopularity extends JsonRecord {
  team: string;
  team_popularity_score: number;
  aggregate_projection: number;
  top5_projection: number;
  hitter_count: number;
  aggregate_projected_ownership: number;
}

export interface OwnershipSnapshot extends TimestampFields, JsonRecord {
  slate_date: string;
  slate_id?: string | null;
  model_version: string;
  source_dk_player_pool_path?: string;
  pitcher_snapshot_reference?: string | null;
  batter_snapshot_reference?: string | null;
  player_count: number;
  players: OwnershipPlayer[];
  team_popularity: Record<string, TeamPopularity>;
  normalization_checks: JsonRecord;
}

// ---------------------------------------------------------------------------
// DK player pool
// ---------------------------------------------------------------------------

export interface DFSPlayer extends JsonRecord {
  dk_player_id: string;
  name: string;
  team: string;
  player_type: "pitcher" | "hitter";
  dk_positions: string[];
  salary: number;
  mlb_player_id: string | null;
  opponent: string | null;
  game_id: string | null;
  batting_order: number | null;
  throwing_hand?: string | null;
  batting_hand?: string | null;
  projection: number | null;
  ceiling: number | null;
  floor: number | null;
  overall_score: number | null;
  risk_score: number | null;
  confidence: number | null;
  tags: string[];
  reasons: string[];
  season_sample_size: number | null;
  lineup_status: string;
  match_status: string;
  /** Milestone 30.1: explicit playing-status/optimizer-eligibility layer
   * -- see dfs/eligibility.py. STARTING_PITCHER | STARTING_HITTER |
   * LINEUP_UNCONFIRMED | BENCH | RELIEF_PITCHER | SCRATCHED | UNMATCHED |
   * AMBIGUOUS. Optional only so pool files saved before this milestone
   * (which lack the field) don't fail to parse -- readers should treat a
   * missing value as UNMATCHED/not eligible, never assume eligibility. */
  eligibility_status?: string;
  optimizer_eligible?: boolean;
}

export interface DKPlayerPool extends JsonRecord {
  slate_date: string;
  generated_at_utc: string;
  csv_source?: string;
  pitcher_snapshot_path: string | null;
  batter_snapshot_path: string | null;
  roster_feasibility?: JsonRecord;
  roster_feasibility_pass?: boolean;
  player_count: number;
  players: DFSPlayer[];
  /** Milestone 26: set by scripts/build_dfs_pool_from_provider.py's
   * save_pool(extra_metadata=...) call -- which specific provider slate
   * this pool was built for, when built via the provider pipeline
   * (never set for the older manual --csv build path). */
  selected_slate_id?: string | null;
}

// ---------------------------------------------------------------------------
// Optimizer lineup set
// ---------------------------------------------------------------------------

export interface LineupAssignment extends JsonRecord {
  slot: string;
  dk_player_id: string;
  mlb_player_id: string | null;
  name: string;
  team: string;
  opponent: string | null;
  salary: number;
  projection: number;
  ceiling: number;
  floor: number | null;
  risk_score: number | null;
  confidence: number | null;
  projected_ownership: number | null;
}

export interface Lineup extends JsonRecord {
  index: number;
  assignments: LineupAssignment[];
  salary: number;
  remaining_salary: number;
  projection: number;
  ceiling: number;
  floor: number;
  average_risk: number | null;
  average_confidence: number | null;
  team_counts: Record<string, number>;
  primary_stack_team: string | null;
  primary_stack_size: number;
  sum_ownership: number | null;
  average_ownership: number | null;
  max_ownership: number | null;
  players_above_chalk_threshold: number | null;
}

export interface LineupSet extends TimestampFields, JsonRecord {
  slate_date: string;
  optimizer_version: string;
  source_player_pool_path: string;
  pitcher_snapshot_reference?: string | null;
  batter_snapshot_reference?: string | null;
  ownership_snapshot_reference?: string | null;
  settings: JsonRecord & { objective_mode?: string };
  lineups_requested: number;
  lineups_generated: number;
  stopped_reason: string | null;
  lineups: Lineup[];
}

// ---------------------------------------------------------------------------
// Evaluations
// ---------------------------------------------------------------------------

export interface PitcherEvaluation extends JsonRecord {
  slate_date: string;
  model_version: string;
  generated_at: string;
  snapshot_path: string | null;
  pitcher_count_predicted: number;
  slate_metrics: {
    pitchers_evaluated: number;
    mae: number | null;
    rmse: number | null;
    projection_correlation: number | null;
    overall_score_correlation: number | null;
  };
  top5_hit_rate: number | null;
  top10_hit_rate: number | null;
  best_calls: JsonRecord[];
  worst_calls: JsonRecord[];
  biggest_positive_surprises: JsonRecord[];
  biggest_busts: JsonRecord[];
  tag_performance: JsonRecord[];
  records: JsonRecord[];
}

export interface OwnershipEvaluation extends TimestampFields, JsonRecord {
  slate_date: string;
  ownership_model_version: string;
  evaluator_version: string;
  contest_id: string | null;
  contest_name: string | null;
  contest_size: number | null;
  matched_count: number;
  match_rate: number;
  overall_metrics: {
    count: number;
    mae: number | null;
    rmse: number | null;
    correlation: number | null;
    rank_correlation: number | null;
    bias: number | null;
  };
  pitcher_metrics: OwnershipEvaluation["overall_metrics"];
  hitter_metrics: OwnershipEvaluation["overall_metrics"];
  chalk_evaluation: { precision: number | null; recall: number | null };
  biggest_under_projections: JsonRecord[];
  biggest_over_projections: JsonRecord[];
  tag_performance: JsonRecord[];
  team_popularity_evaluation: JsonRecord[];
  records: JsonRecord[];
}

// ---------------------------------------------------------------------------
// Dashboard-facing composite types
// ---------------------------------------------------------------------------

export type ArtifactState = "ready" | "missing" | "outdated";

export interface ArtifactStatus {
  label: string;
  state: ArtifactState;
  path: string | null;
  generatedAtUtc: string | null;
  generatedAtLocal: string | null;
  detail?: string;
}

/** One normalized table/search row, built by joining a pitcher or
 * batter snapshot record with (when available) its matching ownership
 * projection and DK player-pool salary/status. `raw` keeps the original
 * source records for the player detail panel. */
export interface PlayerRow {
  id: string; // mlb player_id when known, else the snapshot's own player_id
  playerType: "pitcher" | "hitter";
  name: string;
  team: string;
  opponent: string | null;
  gameId: string | null;
  position: string | null;
  positions: string[];
  battingOrder: number | null;
  salary: number | null;
  projection: number | null;
  ceiling: number | null;
  floor: number | null;
  overall: number | null;
  power: number | null;
  matchup: number | null;
  risk: number | null;
  confidence: number | null;
  ownership: number | null;
  ownershipTier: string | null;
  chalkScore: number | null;
  leverage: number | null;
  tags: string[];
  reasons: string[];
  // Milestone 27.2: every DK-salaried player is preserved as a row even
  // when their research-board record doesn't exist yet (e.g. their
  // team's starting lineup hasn't posted) -- these two fields are how a
  // page tells "confirmed and scored" apart from "real DK player,
  // awaiting lineup confirmation" instead of the player silently
  // vanishing. Mirrors dfs/pool_builder.py's own lineup_status/
  // match_status vocabulary exactly (see DFSPlayer). null only when no
  // DK pool was loaded at all (pool-free callers/tests).
  lineupStatus: string | null;
  matchStatus: string | null;
  // Milestone 30.1: the explicit playing-status/optimizer-eligibility
  // layer (dfs/eligibility.py) -- STARTING_PITCHER | STARTING_HITTER |
  // LINEUP_UNCONFIRMED | BENCH | RELIEF_PITCHER | SCRATCHED | UNMATCHED |
  // AMBIGUOUS. null only when no DK pool was loaded (pool-free callers/
  // tests) or the pool predates this milestone.
  eligibilityStatus: string | null;
  optimizerEligible: boolean;
  // Milestone 32.3B: Big Money ML -- independent SHADOW comparison
  // column only (see lib/mlProjections.ts). null for every pitcher row
  // today (Top Pitchers board doesn't join this yet) and for any hitter
  // whose ML projection wasn't a genuinely captured pregame value.
  // Never influences overall/power/matchup/risk/confidence/ownership/
  // leverage or the default ranking -- comparison-only, same discipline
  // as ProjectionLabTable's mlProjection field.
  mlProjection: number | null;
  mlProjectionStatus: string | null;
  raw: {
    snapshot: JsonRecord;
    ownership: OwnershipPlayer | null;
    pool: DFSPlayer | null;
  };
}
