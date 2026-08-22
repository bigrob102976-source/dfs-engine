"""Milestone 32.1 -- pitcher_features.py. No network calls."""

from historical_mlb.pitcher_features import build_pitcher_game_row

BOXSCORE_ENTRY = {
    "player_id": "543135", "name": "Test Pitcher", "team": "NYY", "side": "home",
    "stat": {
        "inningsPitched": "6.1", "battersFaced": 25, "strikeOuts": 7, "baseOnBalls": 2, "hits": 5,
        "earnedRuns": 2, "homeRuns": 1, "hitBatsmen": 0, "wins": True, "losses": False,
        "completeGames": False, "shutouts": False, "numberOfPitches": 98, "strikes": 65,
    },
}

SEASON_LOG = [
    {"date": "2025-06-05", "stat": {"inningsPitched": "6.0", "battersFaced": 24, "strikeOuts": 6, "baseOnBalls": 1, "hits": 4, "earnedRuns": 1, "homeRuns": 0, "numberOfPitches": 92}},
    {"date": "2025-06-10", "stat": {"inningsPitched": "5.2", "battersFaced": 23, "strikeOuts": 8, "baseOnBalls": 3, "hits": 6, "earnedRuns": 3, "homeRuns": 1, "numberOfPitches": 101}},
    # Target date's own entry -- must never contribute to rolling stats.
    {"date": "2025-06-15", "stat": {"inningsPitched": "9.0", "battersFaced": 27, "strikeOuts": 15, "baseOnBalls": 0, "hits": 0, "earnedRuns": 0, "homeRuns": 0, "numberOfPitches": 100}},
]

OPPONENT_OFFENSE = {"k_pct": 0.22, "bb_pct": 0.08, "hr_rate": 0.03, "woba": 0.32, "sample_games": 10, "sample_pa": 350}


def _base_kwargs(**overrides):
    kwargs = dict(
        game_pk=777505, game_date="2025-06-15", game_number=1, player_id="543135", player_name="Test Pitcher",
        team="NYY", opponent="BOS", home_away="home", game_start_time="2025-06-15T22:40:00Z", venue_id=3313,
        bat_hand="R", throw_hand="R", boxscore_entry=BOXSCORE_ENTRY, starter_flag=True, season_game_log=SEASON_LOG,
        statcast_window_rows=[], opponent_season_offense=OPPONENT_OFFENSE,
        weather={"temperature_2m": 70.0, "wind_speed_10m": 5.0, "wind_direction_10m": 180, "precipitation": 0.0, "relative_humidity_2m": 60},
        venue_roof_type="open",
    )
    kwargs.update(overrides)
    return kwargs


def test_innings_notation_not_misparsed_as_decimal():
    """The exact bug the milestone spec calls out: 6.1 IP = 19 outs, NOT 6.1 decimal."""
    row = build_pitcher_game_row(**_base_kwargs())
    assert row["actual_outs_recorded"] == 19  # 6*3 + 1
    assert row["actual_ip_display"] == "6.1"


def test_actual_outcomes_and_dk_points():
    row = build_pitcher_game_row(**_base_kwargs())
    assert row["actual_so"] == 7
    assert row["actual_er"] == 2
    assert row["actual_win"] is True
    assert row["actual_pitch_count"] == 98
    assert row["actual_dk_points"] is not None


def test_quality_start_true_when_6_plus_ip_and_3_or_fewer_er():
    row = build_pitcher_game_row(**_base_kwargs())
    assert row["actual_quality_start"] is True  # 19 outs (6.1 IP) >= 18, 2 ER <= 3


def test_quality_start_false_when_earned_runs_too_high():
    entry = {**BOXSCORE_ENTRY, "stat": {**BOXSCORE_ENTRY["stat"], "earnedRuns": 5}}
    row = build_pitcher_game_row(**_base_kwargs(boxscore_entry=entry))
    assert row["actual_quality_start"] is False


def test_rolling_stats_exclude_target_game_itself():
    row = build_pitcher_game_row(**_base_kwargs())
    assert row["rolling_starts_season"] == 2  # only 06-05 and 06-10, NOT the 06-15 target-date 9-K entry
    assert row["rolling_so_season"] == 14  # 6 + 8, excludes the target date's 15 K


def test_days_rest_and_previous_pitch_count():
    row = build_pitcher_game_row(**_base_kwargs())
    assert row["days_rest"] == 5  # 06-10 -> 06-15
    assert row["previous_start_pitch_count"] == 101  # from the 06-10 entry, the most recent PRIOR start


def test_opponent_offense_features_passed_through():
    row = build_pitcher_game_row(**_base_kwargs())
    assert row["opponent_k_pct_season"] == 0.22
    assert row["opponent_sample_games"] == 10


def test_starter_flag_and_historical_unavailable_fields():
    row = build_pitcher_game_row(**_base_kwargs())
    assert row["starter_flag"] is True
    assert row["draftkings_salary"] is None
    assert row["vegas_moneyline"] is None
    assert row["vegas_total"] is None


def test_relief_pitcher_starter_flag_false():
    row = build_pitcher_game_row(**_base_kwargs(starter_flag=False))
    assert row["starter_flag"] is False
