"""Milestone 32.1, Part 29 -- hard-fail quality gates. No network calls."""

import pytest

from historical_mlb.quality_gates import (
    QualityGateFailure,
    check_cross_game_contamination,
    check_target_fields_not_pregame_features,
    enforce_quality_gates,
    run_quality_gates,
)


def _hitter_row(player_id="1", game_pk=100, **overrides):
    row = {
        "player_id": player_id, "game_pk": game_pk, "game_date": "2025-06-15",
        "team": "NYY", "actual_1b": 1, "rolling_games_season": 10,
    }
    row.update(overrides)
    return row


def _pitcher_row(player_id="2", game_pk=100, **overrides):
    row = {
        "player_id": player_id, "game_pk": game_pk, "game_date": "2025-06-15",
        "team": "NYY", "actual_ip_display": "6.0", "actual_outs_recorded": 18,
        "rolling_games_season": 5,
    }
    row.update(overrides)
    return row


def _game_row(game_pk=100, **overrides):
    row = {"game_pk": game_pk, "date": "2025-06-15", "away_team": "BOS", "home_team": "NYY", "game_number": 1}
    row.update(overrides)
    return row


def test_pitcher_who_also_batted_is_not_a_duplicate_across_tables():
    """Regression guard for the exact bug found live during this
    milestone's dry-run build: a pitcher with a real batting stat line
    (NL rules, no DH) legitimately produces one row in hitter_rows AND
    one row in pitcher_rows for the SAME (player_id, game_pk) -- that
    must never be flagged as a duplicate."""
    hitter_rows = [_hitter_row(player_id="543135", game_pk=1)]
    pitcher_rows = [_pitcher_row(player_id="543135", game_pk=1)]
    findings = run_quality_gates(hitter_rows, pitcher_rows, [_game_row(game_pk=1)])
    assert not any(f["check"] == "duplicate_player_game_row" for f in findings)


def test_genuine_duplicate_within_hitter_table_is_caught():
    hitter_rows = [_hitter_row(player_id="1", game_pk=1), _hitter_row(player_id="1", game_pk=1)]
    findings = run_quality_gates(hitter_rows, [], [_game_row(game_pk=1)])
    assert any(f["check"] == "duplicate_player_game_row" for f in findings)


def test_genuine_duplicate_within_pitcher_table_is_caught():
    pitcher_rows = [_pitcher_row(player_id="2", game_pk=1), _pitcher_row(player_id="2", game_pk=1)]
    findings = run_quality_gates([], pitcher_rows, [_game_row(game_pk=1)])
    assert any(f["check"] == "duplicate_player_game_row" for f in findings)


def test_check_target_fields_not_pregame_features_clean_manifest():
    from historical_mlb.manifest import hitter_manifest
    findings = check_target_fields_not_pregame_features(hitter_manifest(), {})
    assert findings == []


def test_check_cross_game_contamination_flags_decreasing_sample_size():
    rows = [
        {"player_id": "1", "game_date": "2025-06-10", "rolling_games_season": 20},
        {"player_id": "1", "game_date": "2025-06-15", "rolling_games_season": 5},  # impossible: history should only grow
    ]
    findings = check_cross_game_contamination(rows)
    assert len(findings) == 1


def test_check_cross_game_contamination_allows_increasing_sample_size():
    rows = [
        {"player_id": "1", "game_date": "2025-06-10", "rolling_games_season": 5},
        {"player_id": "1", "game_date": "2025-06-15", "rolling_games_season": 20},
    ]
    assert check_cross_game_contamination(rows) == []


def test_check_cross_game_contamination_allows_reset_across_a_season_boundary():
    """Regression guard for a real false-positive caught live while
    validating this milestone's own partial warehouse (which spans a
    genuine gap between the tail of 2024 and the start of 2025 in what
    had been collected so far): rolling_games_season correctly RESETS
    at the start of a new season, so a late-2024 count of 13 followed
    by an early-2025 count of 3 is healthy, not contamination."""
    rows = [
        {"player_id": "1", "game_date": "2024-04-12", "season": 2024, "rolling_games_season": 13},
        {"player_id": "1", "game_date": "2025-06-14", "season": 2025, "rolling_games_season": 8},
    ]
    assert check_cross_game_contamination(rows) == []


def test_check_cross_game_contamination_still_flags_decrease_within_same_season_using_season_field():
    rows = [
        {"player_id": "1", "game_date": "2025-06-10", "season": 2025, "rolling_games_season": 20},
        {"player_id": "1", "game_date": "2025-06-15", "season": 2025, "rolling_games_season": 5},
    ]
    findings = check_cross_game_contamination(rows)
    assert len(findings) == 1


def test_enforce_quality_gates_raises_on_blocking_violation():
    hitter_rows = [_hitter_row(player_id="1", game_pk=1), _hitter_row(player_id="1", game_pk=1)]
    with pytest.raises(QualityGateFailure) as exc_info:
        enforce_quality_gates(hitter_rows, [], [_game_row(game_pk=1)])
    assert len(exc_info.value.findings) >= 1


def test_enforce_quality_gates_passes_clean_data():
    findings = enforce_quality_gates([_hitter_row()], [_pitcher_row()], [_game_row()])
    assert isinstance(findings, list)  # no exception


def test_enforce_quality_gates_catches_negative_singles():
    hitter_rows = [_hitter_row(actual_1b=-1)]
    with pytest.raises(QualityGateFailure):
        enforce_quality_gates(hitter_rows, [], [_game_row()])


def test_enforce_quality_gates_catches_doubleheader_collision():
    games = [_game_row(game_pk=1, game_number=1), _game_row(game_pk=2, game_number=1)]  # same date/teams, both "game 1"
    with pytest.raises(QualityGateFailure):
        enforce_quality_gates([], [], games)
