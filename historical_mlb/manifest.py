"""Milestone 32.1, Parts 22/23 -- the feature manifest: single source of
truth for every column hitter_features.py / pitcher_features.py
produce, its availability class, and whether it's a target/outcome
column. This is the ENFORCEMENT layer for Part 24's anti-leakage rule:
quality_gates.py's `assert_no_target_leakage_in_features` reads this
manifest to decide which columns are forbidden on the pregame feature
side, so a new column added to a feature builder without a matching
manifest entry fails loudly (a test enforces this too -- see
tests/test_historical_mlb_manifest.py) rather than silently slipping
through unclassified.

Availability classes (Part 22):
    ALWAYS_PREGAME         -- safe for a model that must run before
                               lineups are announced (e.g. season-long
                               rolling rates, handedness, venue).
    PREGAME_AFTER_LINEUPS  -- only safe once lineups are confirmed
                               (confirmed batting order, confirmed
                               starter identity for that specific game).
    HISTORICAL_OUTCOME_ONLY -- a real observation, but only knowable
                               AFTER the game (actual counting stats)
                               -- never a model feature, only useful for
                               retrospective analysis/backtesting.
    TARGET                 -- the model's prediction target
                               (actual_dk_points). The strictest class:
                               never a feature under any circumstance.
"""

from dataclasses import dataclass
from typing import List

ALWAYS_PREGAME = "ALWAYS_PREGAME"
PREGAME_AFTER_LINEUPS = "PREGAME_AFTER_LINEUPS"
HISTORICAL_OUTCOME_ONLY = "HISTORICAL_OUTCOME_ONLY"
TARGET = "TARGET"

VALID_CLASSES = {ALWAYS_PREGAME, PREGAME_AFTER_LINEUPS, HISTORICAL_OUTCOME_ONLY, TARGET}


@dataclass
class FeatureDef:
    name: str
    entity: str  # "hitter" | "pitcher" | "game"
    dtype: str
    description: str
    source: str
    availability_class: str
    target_flag: bool
    leakage_risk: str  # "none" | "low" | "high" -- a documented judgment call, not a computed value

    def __post_init__(self):
        if self.availability_class not in VALID_CLASSES:
            raise ValueError(f"Unknown availability_class {self.availability_class!r} for feature {self.name!r}")
        if self.target_flag and self.availability_class != TARGET:
            raise ValueError(f"Feature {self.name!r} has target_flag=True but availability_class != TARGET")


def _identity_fields(entity: str) -> List[FeatureDef]:
    return [
        FeatureDef("season", entity, "int", "MLB season year", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("game_date", entity, "str", "Official game date (YYYY-MM-DD)", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("game_pk", entity, "int", "Canonical MLB game id", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("game_number", entity, "int", "1 or 2 -- doubleheader-safe", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("player_id", entity, "str", "Canonical MLBAM player id", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("player_name", entity, "str", "Player display name", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("team", entity, "str", "Player's team abbreviation for this game", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("opponent", entity, "str", "Opposing team abbreviation", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("home_away", entity, "str", "'home' or 'away'", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("game_start_time", entity, "str", "Scheduled UTC start time", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("venue_id", entity, "int", "MLB venue id", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("bat_hand", entity, "str", "Batting handedness", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
        FeatureDef("throw_hand", entity, "str", "Throwing handedness", "mlb_stats_api", ALWAYS_PREGAME, False, "none"),
    ]


_HITTER_ROLLING_STATS = ["pa", "ab", "h", "1b", "2b", "3b", "hr", "bb", "hbp", "r", "rbi", "sb", "so"]
_HITTER_ROLLING_DERIVED = ["avg", "obp", "slg", "ops", "iso", "k_pct", "bb_pct", "hr_per_pa", "sb_per_pa"]
_ROLLING_WINDOWS = ["7d", "14d", "30d", "season"]


def hitter_manifest() -> List[FeatureDef]:
    fields = _identity_fields("hitter")

    for window in _ROLLING_WINDOWS:
        for stat in _HITTER_ROLLING_STATS:
            fields.append(FeatureDef(
                f"rolling_{stat}_{window}", "hitter", "int", f"Rolling {stat} over {window} (pregame, excludes target game)",
                "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none",
            ))
        for stat in _HITTER_ROLLING_DERIVED:
            fields.append(FeatureDef(
                f"rolling_{stat}_{window}", "hitter", "float", f"Rolling {stat} over {window} (pregame, excludes target game)",
                "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none",
            ))
        fields.append(FeatureDef(f"rolling_games_{window}", "hitter", "int", f"Sample size (games) for the {window} window", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"))

    for window in ["14d", "30d", "season"]:
        for stat in ["avg_exit_velocity", "avg_launch_angle", "hard_hit_rate", "barrel_rate", "xwoba", "xslg"]:
            fields.append(FeatureDef(f"statcast_{stat}_{window}", "hitter", "float", f"Statcast {stat} over {window} (pregame)", "baseball_savant", ALWAYS_PREGAME, False, "none"))
        fields.append(FeatureDef(f"statcast_batted_balls_{window}", "hitter", "int", f"Statcast batted-ball sample size for {window}", "baseball_savant", ALWAYS_PREGAME, False, "none"))

    for platoon in ["vs_lhp", "vs_rhp"]:
        for stat in ["pa", "avg", "obp", "slg", "woba"]:
            fields.append(FeatureDef(
                f"platoon_{platoon}_{stat}", "hitter", "float",
                f"Trailing-30-day platoon split {platoon} {stat} (pregame; derived from Statcast per-pitch outcomes, NOT a full-season split -- see manifest module docstring)",
                "baseball_savant", ALWAYS_PREGAME, False, "none",
            ))

    fields += [
        FeatureDef("opposing_starting_pitcher_id", "hitter", "str", "Opposing probable/actual starter's MLBAM id", "mlb_stats_api", PREGAME_AFTER_LINEUPS, False, "low"),
        FeatureDef("opposing_starting_pitcher_hand", "hitter", "str", "Opposing starter's throwing hand", "mlb_stats_api", PREGAME_AFTER_LINEUPS, False, "low"),
        FeatureDef("opposing_pitcher_era_season", "hitter", "float", "Opposing starter's season ERA through the day before this game", "mlb_stats_api_gamelog", PREGAME_AFTER_LINEUPS, False, "low"),
        FeatureDef("opposing_pitcher_k_pct_season", "hitter", "float", "Opposing starter's season K% through the day before this game", "mlb_stats_api_gamelog", PREGAME_AFTER_LINEUPS, False, "low"),

        FeatureDef("batting_order_actual", "hitter", "int", "Actual lineup slot batted -- ONLY usable by a post-lineup model", "mlb_stats_api_boxscore", PREGAME_AFTER_LINEUPS, False, "high"),
        FeatureDef("lineup_availability", "hitter", "str", "'confirmed' or 'unconfirmed' -- gates whether batting_order_actual is usable", "mlb_stats_api_boxscore", ALWAYS_PREGAME, False, "none"),

        FeatureDef("weather_temperature_f", "hitter", "float", "Home-venue temperature at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_wind_speed_mph", "hitter", "float", "Home-venue wind speed at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_wind_direction_deg", "hitter", "float", "Home-venue wind direction at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_precipitation", "hitter", "float", "Home-venue precipitation at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_humidity_pct", "hitter", "float", "Home-venue relative humidity at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_available", "hitter", "bool", "Whether a real weather observation was found", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_source", "hitter", "str", "'open_meteo' or null", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("venue_roof_type", "hitter", "str", "open/retractable/dome -- context for interpreting weather", "config_static", ALWAYS_PREGAME, False, "none"),

        FeatureDef("draftkings_salary", "hitter", "float", "Historical DK salary -- NOT_AVAILABLE for V1, always null", "historical_dk_salary_unavailable", ALWAYS_PREGAME, False, "none"),
        FeatureDef("vegas_team_total", "hitter", "float", "Historical implied team total -- incomplete for V1, nullable", "historical_vegas_incomplete", ALWAYS_PREGAME, False, "none"),
    ]

    fields += [
        FeatureDef("actual_pa", "hitter", "int", "Actual plate appearances", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_ab", "hitter", "int", "Actual at-bats", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_h", "hitter", "int", "Actual hits", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_1b", "hitter", "int", "Actual singles (H - 2B - 3B - HR)", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_2b", "hitter", "int", "Actual doubles", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_3b", "hitter", "int", "Actual triples", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_hr", "hitter", "int", "Actual home runs", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_bb", "hitter", "int", "Actual walks", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_hbp", "hitter", "int", "Actual hit-by-pitch", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_r", "hitter", "int", "Actual runs", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_rbi", "hitter", "int", "Actual RBI", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_sb", "hitter", "int", "Actual stolen bases", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_cs", "hitter", "int", "Actual caught stealing", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_so", "hitter", "int", "Actual strikeouts", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_dk_points", "hitter", "float", "Actual DraftKings fantasy points (model target)", "evaluation.dk_actual_scoring", TARGET, True, "high"),
    ]
    return fields


_PITCHER_ROLLING_STATS = ["outs", "ip", "bf", "so", "bb", "h", "hr", "er", "pitch_count"]
_PITCHER_ROLLING_DERIVED = ["k_pct", "bb_pct", "k_minus_bb_pct", "era", "whip", "hr_rate"]


def pitcher_manifest() -> List[FeatureDef]:
    fields = _identity_fields("pitcher")

    for window in _ROLLING_WINDOWS:
        for stat in _PITCHER_ROLLING_STATS:
            fields.append(FeatureDef(
                f"rolling_{stat}_{window}", "pitcher", "float" if stat == "ip" else "int",
                f"Rolling {stat} over {window} (pregame, excludes target game)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none",
            ))
        for stat in _PITCHER_ROLLING_DERIVED:
            fields.append(FeatureDef(f"rolling_{stat}_{window}", "pitcher", "float", f"Rolling {stat} over {window} (pregame, excludes target game)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"))
        fields.append(FeatureDef(f"rolling_starts_{window}", "pitcher", "int", f"Sample size (starts) for the {window} window", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"))

    fields += [
        FeatureDef("days_rest", "pitcher", "int", "Days since this pitcher's previous appearance", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
        FeatureDef("previous_start_pitch_count", "pitcher", "int", "Pitch count from this pitcher's immediately prior appearance", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
        FeatureDef("starts_last_30d", "pitcher", "int", "Number of starts in the trailing 30 days (pregame)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
        FeatureDef("innings_last_30d", "pitcher", "float", "Innings pitched in the trailing 30 days (pregame)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
    ]

    for window in ["14d", "30d", "season"]:
        for stat in ["avg_exit_velocity_allowed", "avg_launch_angle_allowed", "hard_hit_rate_allowed", "barrel_rate_allowed", "xwoba_allowed", "xslg_allowed"]:
            fields.append(FeatureDef(f"statcast_{stat}_{window}", "pitcher", "float", f"Statcast {stat} over {window} (pregame)", "baseball_savant", ALWAYS_PREGAME, False, "none"))
        fields.append(FeatureDef(f"statcast_batted_balls_allowed_{window}", "pitcher", "int", f"Statcast batted-ball-allowed sample size for {window}", "baseball_savant", ALWAYS_PREGAME, False, "none"))

    for platoon in ["vs_lhb", "vs_rhb"]:
        for stat in ["bf", "avg_allowed", "obp_allowed", "slg_allowed", "woba_allowed"]:
            fields.append(FeatureDef(
                f"platoon_{platoon}_{stat}", "pitcher", "float",
                f"Trailing-30-day platoon split {platoon} {stat} (pregame; derived from Statcast per-pitch outcomes, NOT a full-season split -- see manifest module docstring)",
                "baseball_savant", ALWAYS_PREGAME, False, "none",
            ))

    fields += [
        FeatureDef("starter_flag", "pitcher", "bool", "Whether this pitcher started the game", "mlb_stats_api_boxscore", PREGAME_AFTER_LINEUPS, False, "low"),
        FeatureDef("opponent_k_pct_season", "pitcher", "float", "Opposing team's season-to-date K% (pregame)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
        FeatureDef("opponent_bb_pct_season", "pitcher", "float", "Opposing team's season-to-date BB% (pregame)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
        FeatureDef("opponent_hr_rate_season", "pitcher", "float", "Opposing team's season-to-date HR rate (pregame)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
        FeatureDef("opponent_woba_season", "pitcher", "float", "Opposing team's season-to-date wOBA proxy (pregame)", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),
        FeatureDef("opponent_sample_games", "pitcher", "int", "Games contributing to the opponent offense sample", "mlb_stats_api_gamelog", ALWAYS_PREGAME, False, "none"),

        FeatureDef("weather_temperature_f", "pitcher", "float", "Home-venue temperature at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_wind_speed_mph", "pitcher", "float", "Home-venue wind speed at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_wind_direction_deg", "pitcher", "float", "Home-venue wind direction at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_precipitation", "pitcher", "float", "Home-venue precipitation at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_humidity_pct", "pitcher", "float", "Home-venue relative humidity at game hour", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_available", "pitcher", "bool", "Whether a real weather observation was found", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("weather_source", "pitcher", "str", "'open_meteo' or null", "open_meteo", ALWAYS_PREGAME, False, "none"),
        FeatureDef("venue_roof_type", "pitcher", "str", "open/retractable/dome -- context for interpreting weather", "config_static", ALWAYS_PREGAME, False, "none"),

        FeatureDef("draftkings_salary", "pitcher", "float", "Historical DK salary -- NOT_AVAILABLE for V1, always null", "historical_dk_salary_unavailable", ALWAYS_PREGAME, False, "none"),
        FeatureDef("vegas_moneyline", "pitcher", "float", "Historical moneyline -- incomplete for V1, nullable", "historical_vegas_incomplete", ALWAYS_PREGAME, False, "none"),
        FeatureDef("vegas_total", "pitcher", "float", "Historical game total -- incomplete for V1, nullable", "historical_vegas_incomplete", ALWAYS_PREGAME, False, "none"),
    ]

    fields += [
        FeatureDef("actual_outs_recorded", "pitcher", "int", "Actual outs recorded", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_ip_display", "pitcher", "str", "Actual innings pitched, baseball notation", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_bf", "pitcher", "int", "Actual batters faced", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_h", "pitcher", "int", "Actual hits allowed", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_hr", "pitcher", "int", "Actual home runs allowed", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_bb", "pitcher", "int", "Actual walks allowed", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_hbp", "pitcher", "int", "Actual hit batsmen", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_so", "pitcher", "int", "Actual strikeouts", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_er", "pitcher", "int", "Actual earned runs", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_pitch_count", "pitcher", "int", "Actual pitch count", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_strikes", "pitcher", "int", "Actual strikes thrown", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_win", "pitcher", "bool", "Actual decision: win", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_loss", "pitcher", "bool", "Actual decision: loss", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_quality_start", "pitcher", "bool", "6+ IP and <=3 ER", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_complete_game", "pitcher", "bool", "Actual complete game", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_shutout", "pitcher", "bool", "Actual shutout", "mlb_stats_api_boxscore", HISTORICAL_OUTCOME_ONLY, False, "high"),
        FeatureDef("actual_dk_points", "pitcher", "float", "Actual DraftKings fantasy points (model target)", "evaluation.dk_actual_scoring", TARGET, True, "high"),
    ]
    return fields


def full_manifest() -> List[FeatureDef]:
    return hitter_manifest() + pitcher_manifest()


def target_column_names(entity: str) -> List[str]:
    fields = hitter_manifest() if entity == "hitter" else pitcher_manifest()
    return [f.name for f in fields if f.target_flag]


def pregame_safe_column_names(entity: str, include_after_lineups: bool) -> List[str]:
    """Columns a model is allowed to train on -- Part 22's whole point.
    `include_after_lineups=False` -> pre-lineup model (ALWAYS_PREGAME
    only). `True` -> post-lineup model (ALWAYS_PREGAME +
    PREGAME_AFTER_LINEUPS)."""
    fields = hitter_manifest() if entity == "hitter" else pitcher_manifest()
    allowed = {ALWAYS_PREGAME} | ({PREGAME_AFTER_LINEUPS} if include_after_lineups else set())
    return [f.name for f in fields if f.availability_class in allowed]
