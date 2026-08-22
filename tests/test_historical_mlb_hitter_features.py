"""Milestone 32.1 -- hitter_features.py. No network calls; all inputs
are hand-built fixtures matching the real API shapes confirmed live
during this milestone's audit/build."""

from historical_mlb.hitter_features import build_hitter_game_row

BOXSCORE_ENTRY = {
    "player_id": "656716", "name": "Test Hitter", "team": "DET", "side": "home",
    "stat": {"plateAppearances": 4, "atBats": 4, "hits": 2, "doubles": 1, "triples": 0, "homeRuns": 1, "rbi": 3, "runs": 2, "baseOnBalls": 0, "hitByPitch": 0, "stolenBases": 0, "strikeOuts": 1},
}

SEASON_LOG = [
    {"date": "2025-06-10", "stat": {"plateAppearances": 4, "atBats": 4, "hits": 2, "doubles": 0, "triples": 0, "homeRuns": 0, "baseOnBalls": 0, "hitByPitch": 0, "sacFlies": 0, "strikeOuts": 1, "stolenBases": 0, "runs": 1, "rbi": 1}},
    # Same-day entry (the target game itself, or a doubleheader game-1) -- MUST be excluded (Part 24).
    {"date": "2025-06-15", "stat": {"plateAppearances": 5, "atBats": 5, "hits": 5, "doubles": 0, "triples": 0, "homeRuns": 3, "baseOnBalls": 0, "hitByPitch": 0, "sacFlies": 0, "strikeOuts": 0, "stolenBases": 0, "runs": 3, "rbi": 5}},
]


def _base_kwargs(**overrides):
    kwargs = dict(
        game_pk=777505, game_date="2025-06-15", game_number=1, player_id="656716", player_name="Test Hitter",
        team="DET", opponent="CIN", home_away="home", game_start_time="2025-06-15T22:40:00Z", venue_id=2394,
        bat_hand="R", throw_hand="R", boxscore_entry=BOXSCORE_ENTRY, season_game_log=SEASON_LOG,
        statcast_window_rows=[], opposing_starter_id="489119", opposing_starter_hand="L",
        opposing_starter_season_era=3.5, opposing_starter_season_k_pct=0.25,
        batting_order_actual=3, lineup_confirmed=True,
        weather={"temperature_2m": 76.3, "wind_speed_10m": 8.3, "wind_direction_10m": 66, "precipitation": 0.0, "relative_humidity_2m": 55},
        venue_roof_type="open",
    )
    kwargs.update(overrides)
    return kwargs


def test_identity_fields():
    row = build_hitter_game_row(**_base_kwargs())
    assert row["season"] == 2025
    assert row["game_pk"] == 777505
    assert row["player_id"] == "656716"
    assert row["team"] == "DET"
    assert row["opponent"] == "CIN"
    assert row["bat_hand"] == "R"


def test_actual_outcomes_and_dk_points():
    row = build_hitter_game_row(**_base_kwargs())
    assert row["actual_pa"] == 4
    assert row["actual_hr"] == 1
    assert row["actual_2b"] == 1
    assert row["actual_1b"] == 0  # 2 hits - 1 double - 0 triple - 1 hr = 0
    assert row["actual_rbi"] == 3
    assert row["actual_dk_points"] is not None
    assert row["actual_dk_points"] > 0


def test_rolling_stats_exclude_target_game_itself():
    """Regression guard for Part 24: the target game's own entry in the
    season log (2025-06-15, 5-for-5 with 3 HR) must NEVER be counted in
    rolling_season -- only the 2025-06-10 entry should contribute."""
    row = build_hitter_game_row(**_base_kwargs())
    assert row["rolling_games_season"] == 1  # only 06-10, not the 06-15 target-date entry
    assert row["rolling_hr_season"] == 0  # the 3-HR game on the target date must be excluded


def test_rolling_stats_zero_history_returns_none_not_crash():
    row = build_hitter_game_row(**_base_kwargs(season_game_log=[]))
    assert row["rolling_games_season"] == 0
    assert row["rolling_avg_season"] is None


def test_batting_order_and_lineup_availability():
    row = build_hitter_game_row(**_base_kwargs())
    assert row["batting_order_actual"] == 3
    assert row["lineup_availability"] == "confirmed"


def test_weather_fields_populated_when_available():
    row = build_hitter_game_row(**_base_kwargs())
    assert row["weather_available"] is True
    assert row["weather_temperature_f"] == 76.3
    assert row["weather_source"] == "open_meteo"


def test_weather_fields_null_when_unavailable():
    row = build_hitter_game_row(**_base_kwargs(weather=None))
    assert row["weather_available"] is False
    assert row["weather_temperature_f"] is None
    assert row["weather_source"] is None


def test_historical_dk_salary_and_vegas_always_null_never_fabricated():
    row = build_hitter_game_row(**_base_kwargs())
    assert row["draftkings_salary"] is None
    assert row["vegas_team_total"] is None


def test_opposing_starter_matchup_fields():
    row = build_hitter_game_row(**_base_kwargs())
    assert row["opposing_starting_pitcher_id"] == "489119"
    assert row["opposing_starting_pitcher_hand"] == "L"
    assert row["opposing_pitcher_era_season"] == 3.5
