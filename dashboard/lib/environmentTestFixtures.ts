import type { GameEnvironmentReport } from "./gameEnvironment";

/** Shared builder for a fully-populated Game Environment report, used
 * only by tests (mirrors the shape research/game_environment/models.py's
 * GameEnvironmentReport.to_dict() produces). Callers override just the
 * top-level fields they care about -- e.g. `{ weather: null }` for a
 * missing-weather test -- everything else stays realistic. */
export function buildGameEnvironmentReport(overrides: Partial<GameEnvironmentReport> = {}): GameEnvironmentReport {
  const base: GameEnvironmentReport = {
    game_id: "824238",
    home_team: "DET",
    away_team: "CLE",
    game_datetime_utc: "2026-08-13T23:10:00Z",
    venue_name: "Comerica Park",
    environment_score: { overall: 61.2, pitcher: 38.8, hitter: 61.2, stack: 63.0 },
    summary: {
      headline: "CLE @ DET",
      bullet_points: [
        "Balanced offensive environment.",
        "Notable wind blowing out.",
        "No rain concerns.",
        "High implied total.",
        "Strong bullpen.",
      ],
    },
    future_adjustment_preview: { weather_points: 0.4, vegas_points: 0.3, bullpen_points: 0.2, enabled: false },
    weather: {
      game_id: "824238",
      provider_name: "MOCK WEATHER",
      is_mock: true,
      retrieved_at: "2026-08-13T12:00:00Z",
      roof_status: "open",
      delay_risk_percent: 5,
      postponement_risk_percent: 1,
      current: { temperature_f: 78, humidity_percent: 55, wind_speed_mph: 9, wind_direction_degrees: 45, feels_like_f: 79, rain_percent: 5, air_density: null },
      first_pitch: { temperature_f: 76, humidity_percent: 56, wind_speed_mph: 10, wind_direction_degrees: 45, feels_like_f: 77, rain_percent: 5, air_density: null },
      mid_game: { temperature_f: 72, humidity_percent: 58, wind_speed_mph: 12, wind_direction_degrees: 45, feels_like_f: 72, rain_percent: 8, air_density: null },
      late_game: { temperature_f: 68, humidity_percent: 60, wind_speed_mph: 11, wind_direction_degrees: 45, feels_like_f: 67, rain_percent: 8, air_density: null },
    },
    weather_analysis: {
      game_id: "824238",
      conclusions: [{ code: "wind_out_notable", text: "Notable wind blowing out.", favors: "hitter" }],
    },
    vegas: {
      game_id: "824238",
      home_team: "DET",
      away_team: "CLE",
      provider_name: "MOCK VEGAS",
      is_mock: true,
      retrieved_at: "2026-08-13T12:00:00Z",
      opening_home: { moneyline: -120, run_line: -1.5, run_line_odds: 150, total: 9.0 },
      opening_away: { moneyline: 110, run_line: 1.5, run_line_odds: -170, total: 9.0 },
      current_home: { moneyline: -130, run_line: -1.5, run_line_odds: 145, total: 9.7 },
      current_away: { moneyline: 120, run_line: 1.5, run_line_odds: -165, total: 9.7 },
      home_implied_runs: 5.1,
      away_implied_runs: 4.6,
      total_movement: 0.7,
      moneyline_movement_home: -10,
    },
    ballpark: {
      team_abbr: "DET",
      venue_name: "Comerica Park",
      hr_factor: 95,
      run_factor: 98,
      park_factor: 97,
      altitude_ft: 585,
      roof: "open",
      surface: "grass",
      orientation_degrees: 137,
    },
    umpire: {
      game_id: "824238",
      status: "UNKNOWN",
      name: null,
      strike_percent: null,
      walk_percent: null,
      k_percent: null,
      zone_size_score: null,
      runs_per_game: null,
      tendency: "unknown",
    },
    bullpen_home: {
      team_abbr: "DET",
      provider_name: "MOCK BULLPEN",
      is_mock: true,
      era: 3.9,
      fip: 4.0,
      xfip: 4.1,
      relievers_used_last_3_days: 2,
      estimated_fatigue: "low",
      closer_available: true,
      high_leverage_arms_available: 2,
      strength_score: 62.0,
    },
    bullpen_away: {
      team_abbr: "CLE",
      provider_name: "MOCK BULLPEN",
      is_mock: true,
      era: 4.6,
      fip: 4.5,
      xfip: 4.4,
      relievers_used_last_3_days: 3,
      estimated_fatigue: "high",
      closer_available: false,
      high_leverage_arms_available: 1,
      strength_score: 41.0,
    },
    travel_home: { team_abbr: "DET", opponent_abbr: "CLE", is_home: true, status: "KNOWN", distance_miles: 0, timezones_crossed: 0, back_to_back: null, getaway_day: null },
    travel_away: { team_abbr: "CLE", opponent_abbr: "DET", is_home: false, status: "KNOWN", distance_miles: 90, timezones_crossed: 0, back_to_back: null, getaway_day: null },
  };

  return { ...base, ...overrides };
}
