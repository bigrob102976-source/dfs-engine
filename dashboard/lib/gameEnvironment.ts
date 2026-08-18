import { ARTIFACT_DIRS, artifactPath } from "./artifactRoot";
import { findAllFiles, findLatestFile, safeReadJson } from "./discovery";

export interface WeatherReading {
  temperature_f: number | null;
  humidity_percent: number | null;
  wind_speed_mph: number | null;
  wind_direction_degrees: number | null;
  feels_like_f: number | null;
  rain_percent: number | null;
  air_density: number | null;
}

export interface WeatherSnapshot {
  game_id: string;
  provider_name: string;
  is_mock: boolean;
  retrieved_at: string;
  roof_status: "open" | "closed" | "dome" | "retractable" | "unknown";
  delay_risk_percent: number | null;
  postponement_risk_percent: number | null;
  current: WeatherReading;
  first_pitch: WeatherReading;
  mid_game: WeatherReading;
  late_game: WeatherReading;
}

export interface WeatherConclusion {
  code: string;
  text: string;
  favors: "hitter" | "pitcher" | "neutral" | "risk";
}

export interface WeatherAnalysis {
  game_id: string;
  conclusions: WeatherConclusion[];
}

export interface VegasLine {
  moneyline: number | null;
  run_line: number | null;
  run_line_odds: number | null;
  total: number | null;
}

export interface BookLineSnapshot {
  book: string;
  home_moneyline: number | null;
  away_moneyline: number | null;
  total: number | null;
  total_over_odds: number | null;
  total_under_odds: number | null;
  home_run_line: number | null;
  away_run_line: number | null;
  home_run_line_odds: number | null;
  away_run_line_odds: number | null;
  last_updated: string | null;
}

export interface VegasSnapshot {
  game_id: string;
  home_team: string;
  away_team: string;
  provider_name: string;
  is_mock: boolean;
  retrieved_at: string;
  opening_home: VegasLine;
  opening_away: VegasLine;
  current_home: VegasLine;
  current_away: VegasLine;
  home_implied_runs: number | null;
  away_implied_runs: number | null;
  total_movement: number | null;
  moneyline_movement_home: number | null;

  // Milestone 24: real-provider provenance, per-book detail, and
  // explainable consensus/implied-runs methodology. All None/[] for
  // MockVegasProvider.
  event_id: string | null;
  books: BookLineSnapshot[];
  books_used: string[];
  market_count: number;
  consensus_method: string | null;
  consensus_home_win_probability: number | null;
  consensus_away_win_probability: number | null;

  implied_runs_calculation_method: string | null;
  implied_runs_input_total: number | null;
  implied_runs_input_home_run_line: number | null;
  implied_runs_input_home_moneyline: number | null;
  implied_runs_input_away_moneyline: number | null;
  implied_runs_is_valid: boolean;
  validation_warnings: string[];

  is_first_pull_of_day: boolean;

  // Milestone 25: pregame lock / freeze provenance. `game_status` is the
  // PREGAME/IN_PLAY/FINAL/UNKNOWN classification AT CAPTURE TIME for
  // THIS specific snapshot -- frozen forever, never recomputed against
  // the game's current status. `vegas_projection_status` is the
  // dashboard-ready label this same snapshot object always carries:
  // "LIVE_PREGAME" | "PREGAME_FROZEN" | "MISSING" | "INVALID" | "IN_PLAY_ONLY".
  game_status: "PREGAME" | "IN_PLAY" | "FINAL" | "UNKNOWN";
  is_frozen_pregame: boolean;
  vegas_projection_status: "LIVE_PREGAME" | "PREGAME_FROZEN" | "MISSING" | "INVALID" | "IN_PLAY_ONLY";
}

export interface VegasSlateAnalysis {
  highest_total_game_id: string | null;
  lowest_total_game_id: string | null;
  largest_movement_game_id: string | null;
  biggest_favorite_game_id: string | null;
  biggest_underdog_game_id: string | null;
  sharp_movement_game_ids: string[];
}

export interface BallparkProfile {
  team_abbr: string;
  venue_name: string;
  hr_factor: number;
  run_factor: number;
  park_factor: number;
  altitude_ft: number;
  roof: "open" | "dome" | "retractable";
  surface: "grass" | "turf";
  orientation_degrees: number;
}

export interface UmpireProfile {
  game_id: string;
  status: "KNOWN" | "UNKNOWN";
  name: string | null;
  strike_percent: number | null;
  walk_percent: number | null;
  k_percent: number | null;
  zone_size_score: number | null;
  runs_per_game: number | null;
  tendency: "pitcher_friendly" | "hitter_friendly" | "neutral" | "unknown";
}

export interface BullpenProfile {
  team_abbr: string;
  provider_name: string;
  is_mock: boolean;
  era: number | null;
  fip: number | null;
  xfip: number | null;
  relievers_used_last_3_days: number | null;
  estimated_fatigue: "low" | "medium" | "high" | "unknown";
  closer_available: boolean | null;
  high_leverage_arms_available: number | null;
  strength_score: number | null;
}

export interface TravelProfile {
  team_abbr: string;
  opponent_abbr: string;
  is_home: boolean;
  status: "KNOWN" | "UNKNOWN";
  distance_miles: number | null;
  timezones_crossed: number | null;
  back_to_back: boolean | null;
  getaway_day: boolean | null;
}

export interface EnvironmentScore {
  overall: number;
  pitcher: number;
  hitter: number;
  stack: number;
}

export interface FutureAdjustmentPreview {
  weather_points: number | null;
  vegas_points: number | null;
  bullpen_points: number | null;
  enabled: boolean;
}

export interface GameSummary {
  headline: string;
  bullet_points: string[];
}

export interface GameEnvironmentReport {
  game_id: string;
  home_team: string;
  away_team: string;
  game_datetime_utc: string | null;
  venue_name: string | null;
  environment_score: EnvironmentScore;
  summary: GameSummary;
  future_adjustment_preview: FutureAdjustmentPreview;
  weather: WeatherSnapshot | null;
  weather_analysis: WeatherAnalysis | null;
  vegas: VegasSnapshot | null;
  ballpark: BallparkProfile | null;
  umpire: UmpireProfile | null;
  bullpen_home: BullpenProfile | null;
  bullpen_away: BullpenProfile | null;
  travel_home: TravelProfile | null;
  travel_away: TravelProfile | null;

  // Milestone 25: `vegas` above is ALWAYS the pregame-safe value Native/AI
  // consume (live pregame, frozen pregame, or None) -- never replaced by
  // in-play odds. `vegas_live` is the CURRENT market snapshot regardless
  // of game status, for research/history display only (the Vegas
  // Intelligence page's LIVE MARKET tab) -- never read by Native/AI.
  mlb_game_status: string | null;
  game_status: "PREGAME" | "IN_PLAY" | "FINAL" | "UNKNOWN";
  vegas_live: VegasSnapshot | null;
}

export interface SlateEnvironmentReport {
  slate_date: string;
  generated_at: string;
  engine_version: string;
  games: GameEnvironmentReport[];
  vegas_slate_analysis: VegasSlateAnalysis | null;
  warnings: string[];
}

/** Reads the latest immutable Game Environment snapshot for `date`, if
 * any. Pure filesystem read -- never triggers generation (see
 * scripts/build_game_environment_report.py for that). */
export function loadLatestEnvironmentReport(date: string): SlateEnvironmentReport | null {
  const dir = artifactPath(ARTIFACT_DIRS.gameEnvironmentSnapshots, date);
  const path = findLatestFile(dir, "environment_");
  return safeReadJson<SlateEnvironmentReport>(path);
}

/** Milestone 24: EVERY immutable Game Environment snapshot saved for
 * `date`, oldest first -- not just the latest. Used to build genuine
 * intraday Vegas line-movement history (First Observed / Current /
 * High / Low / real sparkline series) from this project's OWN saved
 * snapshots, since a real provider's response is only ever a single
 * point in time; the milestone explicitly forbids fabricating
 * intermediate history points, so this is the one honest source. Pure
 * filesystem read -- never triggers generation. */
export function loadEnvironmentReportHistory(date: string): SlateEnvironmentReport[] {
  const dir = artifactPath(ARTIFACT_DIRS.gameEnvironmentSnapshots, date);
  return findAllFiles(dir, "environment_")
    .map((path) => safeReadJson<SlateEnvironmentReport>(path))
    .filter((report): report is SlateEnvironmentReport => report !== null);
}
