"""Milestone 32.0 -- historical_mlb/audit.py. No network calls."""

from historical_mlb.audit import (
    check_doubleheader_collisions,
    check_duplicate_game_ids,
    check_duplicate_player_game_rows,
    check_future_data_leakage,
    check_impossible_innings,
    check_impossible_negative_counts,
    check_invalid_dates,
    check_missing_handedness,
    check_missing_team_or_opponent,
    check_no_leaked_actuals_in_features,
)


def test_check_duplicate_player_game_rows_flags_exact_duplicate():
    rows = [{"player_id": "1", "game_id": "g1"}, {"player_id": "1", "game_id": "g1"}]
    findings = check_duplicate_player_game_rows(rows)
    assert len(findings) == 1
    assert findings[0]["check"] == "duplicate_player_game_row"


def test_check_duplicate_player_game_rows_allows_same_player_different_games():
    rows = [{"player_id": "1", "game_id": "g1"}, {"player_id": "1", "game_id": "g2"}]
    assert check_duplicate_player_game_rows(rows) == []


def test_check_duplicate_game_ids():
    games = [{"canonical_game_id": "g1"}, {"canonical_game_id": "g1"}]
    findings = check_duplicate_game_ids(games)
    assert len(findings) == 1


def test_check_impossible_negative_counts_flags_negative_hits():
    rows = [{"player_id": "1", "game_id": "g1", "actual_h": -1}]
    findings = check_impossible_negative_counts(rows)
    assert len(findings) == 1
    assert findings[0]["severity"] == "error"


def test_check_impossible_negative_counts_allows_zero():
    rows = [{"player_id": "1", "game_id": "g1", "actual_h": 0}]
    assert check_impossible_negative_counts(rows) == []


def test_check_missing_team_or_opponent():
    rows = [{"player_id": "1", "game_id": "g1", "team": None}]
    findings = check_missing_team_or_opponent(rows)
    assert any(f["check"] == "missing_team" for f in findings)


def test_check_missing_handedness_only_checks_present_keys():
    rows = [{"player_id": "1", "bat_hand": None, "throw_hand": "R"}]
    findings = check_missing_handedness(rows)
    assert len(findings) == 1  # only bat_hand flagged, throw_hand is populated


def test_check_impossible_innings_flags_negative():
    rows = [{"player_id": "1", "game_id": "g1", "actual_ip": -1.0}]
    findings = check_impossible_innings(rows)
    assert len(findings) == 1


def test_check_invalid_dates_flags_bad_format():
    rows = [{"player_id": "1", "game_date": "06/15/2025"}, {"player_id": "2", "game_date": "2025-06-15"}]
    findings = check_invalid_dates(rows)
    assert len(findings) == 1


def test_check_no_leaked_actuals_in_features_flags_actual_prefixed_key():
    features = {"rolling_avg_30d": 0.3, "actual_dk_points": 12.0}
    findings = check_no_leaked_actuals_in_features(features)
    assert len(findings) == 1
    assert "actual_dk_points" in findings[0]["detail"]


def test_check_no_leaked_actuals_in_features_clean_row():
    features = {"rolling_avg_30d": 0.3, "park_factor": 101}
    assert check_no_leaked_actuals_in_features(features) == []


def test_check_future_data_leakage():
    rows = [{"player_id": "1", "game_date": "2025-06-15", "as_of_date": "2025-06-16"}]
    findings = check_future_data_leakage(rows)
    assert len(findings) == 1


def test_check_doubleheader_collisions_flags_missing_game_number_distinction():
    games = [
        {"date": "2025-06-15", "away_team": "CIN", "home_team": "DET", "game_number": 1},
        {"date": "2025-06-15", "away_team": "CIN", "home_team": "DET", "game_number": 1},  # bug: both "1"
    ]
    findings = check_doubleheader_collisions(games)
    assert len(findings) == 1
    assert findings[0]["check"] == "doubleheader_collision"


def test_check_doubleheader_collisions_allows_properly_numbered_games():
    games = [
        {"date": "2025-06-15", "away_team": "CIN", "home_team": "DET", "game_number": 1},
        {"date": "2025-06-15", "away_team": "CIN", "home_team": "DET", "game_number": 2},
    ]
    assert check_doubleheader_collisions(games) == []
