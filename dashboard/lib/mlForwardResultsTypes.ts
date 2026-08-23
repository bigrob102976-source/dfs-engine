// Milestone 32.5: pure types + pure functions shared between the
// server-only loader (lib/mlForwardResults.ts, which touches node:fs/
// node:path and must never be imported by a "use client" component)
// and client components that only need the shape + pure transforms.
// Client components must import from THIS file, never from
// lib/mlForwardResults.ts directly (that would drag fs/path into the
// browser bundle -- Turbopack refuses to build it if they do).

export interface MlForwardGameStatus {
  game_id: string;
  detailed_state: string;
  final: boolean;
}

export interface MlPlayerGradingRecord {
  player_id: string;
  name: string;
  team: string | null;
  opponent: string | null;
  game_id: string | null;
  player_type: "pitcher" | "hitter";
  projection_source: string;
  pregame_projection: number;
  actual_dk: number;
  error: number;
  absolute_error: number;
}

export interface MlLineupPlayerGrade {
  name: string;
  mlb_player_id: string | null;
  slot: string;
  projection: number;
  actual_dk: number | null;
  difference: number | null;
}

export interface MlGradedLineup {
  lineup_index: number;
  salary: number;
  projected: number;
  actual: number | null;
  difference: number | null;
  fully_graded: boolean;
  missing_players: string[];
  players: MlLineupPlayerGrade[];
}

export interface MlLineupGrading {
  projection_source: string;
  lineup_sets_found: number;
  lineups_total: number;
  lineups_fully_graded: number;
  lineups: MlGradedLineup[];
  highest_actual: number | null;
  lowest_actual: number | null;
  average_actual: number | null;
  average_projected: number | null;
  average_projection_error: number | null;
}

export interface MlLineupSourceComparisonEntry {
  lineups_total: number;
  lineups_fully_graded: number;
  average_projected: number | null;
  average_actual: number | null;
  best_actual: number | null;
  worst_actual: number | null;
}

export interface MlSourceMetricsRow {
  source: string;
  shared_sample_n: number;
  dates_included: number;
  mae: number | null;
  rmse: number | null;
  pearson: number | null;
  spearman: number | null;
  avg_top5_hit_rate: number | null;
  avg_top10_hit_rate: number | null;
  avg_top20_hit_rate?: number | null;
}

export interface MlSourceComparison {
  slates_requested: number;
  slates_with_actual_results: number;
  slates_with_ml_pregame_data?: number;
  source_metrics: MlSourceMetricsRow[];
}

export interface MlCeilingThreshold {
  n: number;
  avg_predicted: number | null;
  avg_actual: number | null;
  bias: number | null;
}

export interface MlCeilingMonitor {
  dates_with_ceiling_events: number;
  thresholds: Record<string, MlCeilingThreshold>;
}

export interface MlZeroGameMonitor {
  n: number;
  dates_with_zero_games: number;
  avg_predicted: number | null;
  bias: number | null;
  mae: number | null;
}

export interface MlDisasterPitcherMonitor {
  n: number;
  threshold: number;
  dates_with_disaster_starts: number;
  bias: number | null;
  mae: number | null;
}

export interface MlForwardResultsDocument {
  slate_date: string;
  slate_id: string;
  generated_at: string;
  games_total: number;
  games_final: number;
  all_final: boolean;
  games: MlForwardGameStatus[];
  players_graded: number;
  ml_pitchers_graded: number;
  ml_hitters_graded: number;
  lineups_graded: number;
  player_grading: { pitchers: MlPlayerGradingRecord[]; hitters: MlPlayerGradingRecord[]; combined: MlPlayerGradingRecord[] };
  lineup_grading: MlLineupGrading;
  lineup_source_comparison: Record<string, MlLineupSourceComparisonEntry>;
  source_comparison: { pitchers: MlSourceComparison; hitters: MlSourceComparison; combined: MlSourceComparison };
  ceiling_monitor: MlCeilingMonitor;
  zero_game_monitor: MlZeroGameMonitor;
  disaster_pitcher_monitor: MlDisasterPitcherMonitor;
}

export interface MlModelDisagreementRow {
  player_id: string;
  name: string;
  team: string | null;
  opponent: string | null;
  player_type: "pitcher" | "hitter";
  actual_dk: number | null;
  ml: number | null;
  native: number | null;
  ai: number | null;
  ml_error: number | null;
  native_error: number | null;
  ai_error: number | null;
  ml_vs_native: number | null;
  ml_vs_ai: number | null;
}

/** Milestone 32.5 -- MODEL DISAGREEMENTS: pivots the per-(source,
 * player) grading records (build_all_player_grading_records's output)
 * into one row per player with ML/Native/AI side by side. A player
 * missing from a given source simply shows null for that source's
 * columns -- never a fabricated/copied value from another source. */
export function pivotModelDisagreements(records: MlPlayerGradingRecord[]): MlModelDisagreementRow[] {
  const byPlayer = new Map<string, MlModelDisagreementRow>();
  for (const r of records) {
    let row = byPlayer.get(r.player_id);
    if (!row) {
      row = {
        player_id: r.player_id, name: r.name, team: r.team, opponent: r.opponent, player_type: r.player_type,
        actual_dk: r.actual_dk, ml: null, native: null, ai: null, ml_error: null, native_error: null, ai_error: null,
        ml_vs_native: null, ml_vs_ai: null,
      };
      byPlayer.set(r.player_id, row);
    }
    if (r.projection_source === "big_money_ml") {
      row.ml = r.pregame_projection;
      row.ml_error = r.error;
    } else if (r.projection_source === "native") {
      row.native = r.pregame_projection;
      row.native_error = r.error;
    } else if (r.projection_source === "ai") {
      row.ai = r.pregame_projection;
      row.ai_error = r.error;
    }
  }
  for (const row of byPlayer.values()) {
    row.ml_vs_native = row.ml !== null && row.native !== null ? Math.round((row.ml - row.native) * 100) / 100 : null;
    row.ml_vs_ai = row.ml !== null && row.ai !== null ? Math.round((row.ml - row.ai) * 100) / 100 : null;
  }
  return Array.from(byPlayer.values()).filter((r) => r.ml !== null && (r.native !== null || r.ai !== null));
}
