"""NFL M6A -- targeted tests for historical_nfl/raw_validation.py.
Synthetic polars fixtures only (real-schema field names, small,
hand-built) -- the real-schema proof is the M6A final report's live run."""

import math

import polars as pl

from historical_nfl.raw_validation import (
    validate_play_by_play,
    validate_rosters,
    validate_schedules,
    validate_team_stats,
    validate_weekly_player_stats,
)


def test_schedules_missing_required_column_fails_structurally():
    df = pl.DataFrame({"season": [2025], "week": [1], "game_id": ["g1"]})  # no home_team/away_team/gameday
    result = validate_schedules(df, 2025)
    assert result.passed is False
    assert "home_team" in result.missing_required_columns


def test_schedules_duplicate_game_id_reported_not_dropped():
    df = pl.DataFrame({
        "season": [2025, 2025], "week": [1, 1], "game_id": ["g1", "g1"],
        "home_team": ["PHI", "PHI"], "away_team": ["DAL", "DAL"], "gameday": ["2025-09-04", "2025-09-04"],
    })
    result = validate_schedules(df, 2025)
    assert result.passed is True  # structural contract still satisfied
    assert result.duplicate_key_count == 2  # both rows sharing the key are flagged
    assert result.row_count == 2  # nothing dropped


def test_schedules_unique_teams_counts_home_and_away_union():
    df = pl.DataFrame({
        "season": [2025, 2025], "week": [1, 1], "game_id": ["g1", "g2"],
        "home_team": ["PHI", "SF"], "away_team": ["DAL", "SEA"], "gameday": ["2025-09-04", "2025-09-04"],
    })
    result = validate_schedules(df, 2025)
    assert result.unique_teams == 4
    assert result.unique_games == 2


def _rosters_df(rows):
    return pl.DataFrame({
        "season": [r.get("season", 2025) for r in rows], "week": [r.get("week", 1) for r in rows],
        "gsis_id": [r.get("gsis_id", "00-0000001") for r in rows],
        "full_name": [r.get("full_name", "Player One") for r in rows],
        "team": [r.get("team", "PHI") for r in rows], "position": [r.get("position", "QB") for r in rows],
    })


def test_rosters_missing_gsis_reported_as_missing_identity_not_a_failure():
    df = _rosters_df([{"gsis_id": ""}, {"gsis_id": None}, {"gsis_id": "00-0000002"}])
    result = validate_rosters(df, 2025, 1)
    assert result.passed is True
    assert result.missing_identity_count == 2
    assert result.unique_players == 1


def test_rosters_duplicate_identity_row_reported():
    df = _rosters_df([{"gsis_id": "00-0000001"}, {"gsis_id": "00-0000001"}])
    result = validate_rosters(df, 2025, 1)
    assert result.duplicate_key_count == 2


def test_rosters_empty_gsis_never_counted_as_a_duplicate_of_another_empty():
    """Two different missing-identity rows are not "the same player
    twice" -- only a real, non-empty, repeated GSIS ID is a duplicate."""
    df = _rosters_df([{"gsis_id": ""}, {"gsis_id": ""}, {"gsis_id": None}])
    result = validate_rosters(df, 2025, 1)
    assert result.duplicate_key_count == 0
    assert result.missing_identity_count == 3


def _weekly_stats_df(rows):
    return pl.DataFrame({
        "season": [2025] * len(rows), "week": [1] * len(rows),
        "player_id": [r.get("player_id") for r in rows], "team": [r.get("team", "PHI") for r in rows],
        "position": [r.get("position", "QB") for r in rows], "game_id": [r.get("game_id", "g1") for r in rows],
        "completions": [0] * len(rows), "attempts": [0] * len(rows),
        "passing_yards": [r.get("passing_yards", 0.0) for r in rows], "passing_tds": [0] * len(rows),
        "carries": [0] * len(rows), "rushing_yards": [0] * len(rows), "rushing_tds": [0] * len(rows),
        "receptions": [0] * len(rows), "targets": [0] * len(rows),
        "receiving_yards": [0] * len(rows), "receiving_tds": [0] * len(rows),
    }, schema_overrides={"passing_yards": pl.Float64})


def test_weekly_player_stats_missing_player_id_reported_not_a_failure():
    df = _weekly_stats_df([{"player_id": None}, {"player_id": "00-0000001"}])
    result = validate_weekly_player_stats(df, 2025, 1)
    assert result.passed is True
    assert result.missing_identity_count == 1
    assert result.unique_players == 1


def test_weekly_player_stats_nan_value_flagged_as_invalid_not_missing():
    df = _weekly_stats_df([{"player_id": "00-0000001", "passing_yards": float("nan")}])
    result = validate_weekly_player_stats(df, 2025, 1)
    assert result.invalid_numeric_count == 1


def test_weekly_player_stats_infinite_value_flagged():
    df = _weekly_stats_df([{"player_id": "00-0000001", "passing_yards": float("inf")}])
    result = validate_weekly_player_stats(df, 2025, 1)
    assert result.invalid_numeric_count == 1


def test_weekly_player_stats_real_zero_is_not_flagged():
    df = _weekly_stats_df([{"player_id": "00-0000001", "passing_yards": 0.0}])
    result = validate_weekly_player_stats(df, 2025, 1)
    assert result.invalid_numeric_count == 0


def test_weekly_player_stats_duplicate_key_reported():
    df = _weekly_stats_df([{"player_id": "00-0000001"}, {"player_id": "00-0000001"}])
    result = validate_weekly_player_stats(df, 2025, 1)
    assert result.duplicate_key_count == 2


def test_team_stats_duplicate_team_week_reported():
    df = pl.DataFrame({
        "season": [2025, 2025], "week": [1, 1], "team": ["PHI", "PHI"], "opponent_team": ["DAL", "DAL"],
        "passing_yards": [200.0, 200.0], "rushing_yards": [100.0, 100.0], "passing_tds": [1, 1], "rushing_tds": [1, 1],
    })
    result = validate_team_stats(df, 2025, 1)
    assert result.duplicate_key_count == 2
    assert result.unique_teams == 1


def test_team_stats_missing_required_column_fails():
    df = pl.DataFrame({"season": [2025], "week": [1], "team": ["PHI"]})  # no opponent_team
    result = validate_team_stats(df, 2025, 1)
    assert result.passed is False


def _pbp_df(rows):
    return pl.DataFrame({
        "game_id": [r.get("game_id", "g1") for r in rows], "play_id": [r.get("play_id", 1.0) for r in rows],
        "season": [2025] * len(rows), "week": [1] * len(rows),
        "posteam": [r.get("posteam", "PHI") for r in rows], "defteam": [r.get("defteam", "DAL") for r in rows],
        "epa": [r.get("epa", 0.1) for r in rows], "yardline_100": [50.0] * len(rows),
        "down": [1.0] * len(rows), "ydstogo": [10.0] * len(rows),
    }, schema_overrides={"epa": pl.Float64})


def test_play_by_play_duplicate_game_play_id_reported():
    df = _pbp_df([{"game_id": "g1", "play_id": 1.0}, {"game_id": "g1", "play_id": 1.0}])
    result = validate_play_by_play(df, 2025, 1)
    assert result.duplicate_key_count == 2


def test_play_by_play_nan_epa_flagged():
    df = _pbp_df([{"epa": float("nan")}])
    result = validate_play_by_play(df, 2025, 1)
    assert result.invalid_numeric_count == 1


def test_play_by_play_negative_real_epa_not_flagged():
    """A real, legitimate negative EPA (a bad play) must never be
    confused with an invalid value."""
    df = _pbp_df([{"epa": -1.75}])
    result = validate_play_by_play(df, 2025, 1)
    assert result.invalid_numeric_count == 0


def test_play_by_play_unique_games_and_teams():
    df = _pbp_df([{"game_id": "g1", "posteam": "PHI"}, {"game_id": "g2", "posteam": "SF"}])
    result = validate_play_by_play(df, 2025, 1)
    assert result.unique_games == 2
    assert result.unique_teams == 2
