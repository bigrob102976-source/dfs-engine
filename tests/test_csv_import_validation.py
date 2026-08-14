from dfs.models import PlayerMatch
from external_projections.csv_import.validation import build_validation_summary


def _match(name, team, status, candidate_names=None, candidate_mlb_ids=None):
    return PlayerMatch(
        dk_player_id=f"csv-{name}", dk_name=name, dk_team=team, match_status=status,
        candidate_names=candidate_names or [], candidate_mlb_ids=candidate_mlb_ids or [],
    )


def test_counts_matched_unmatched_ambiguous():
    rows = [
        {"name": "A", "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
        {"name": "B", "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
        {"name": "C", "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
    ]
    matches = [_match("A", "NYY", "matched"), _match("B", "NYY", "unmatched"), _match("C", "NYY", "ambiguous", ["C1", "C2"], ["1", "2"])]
    summary = build_validation_summary(rows, matches, {"NYY", "BOS"})
    assert summary.matched == 1
    assert summary.unmatched == 1
    assert summary.ambiguous == 1
    assert len(summary.needs_review) == 1
    assert summary.needs_review[0].candidate_names == ["C1", "C2"]


def test_duplicate_players_detected_by_normalized_name_and_team():
    rows = [
        {"name": "Aaron Judge", "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
        {"name": "Aaron Judge.", "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
    ]
    summary = build_validation_summary(rows, [], {"NYY", "BOS"})
    assert summary.duplicate_players == 1


def test_different_teams_are_not_duplicates():
    rows = [
        {"name": "Aaron Judge", "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
        {"name": "Aaron Judge", "team": "BOS", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "NYY"},
    ]
    summary = build_validation_summary(rows, [], {"NYY", "BOS"})
    assert summary.duplicate_players == 0


def test_missing_fields_counted():
    rows = [
        {"name": "A", "team": "NYY", "salary": None, "projection": None, "position": None, "opponent": "BOS"},
    ]
    summary = build_validation_summary(rows, [], {"NYY", "BOS"})
    assert summary.missing_salary == 1
    assert summary.missing_projection == 1
    assert summary.missing_position == 1


def test_unknown_teams_and_opponents_reported():
    rows = [
        {"name": "A", "team": "ZZZ", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "YYY"},
    ]
    summary = build_validation_summary(rows, [], {"NYY", "BOS"})
    assert summary.unknown_teams == ["ZZZ"]
    assert summary.unknown_opponents == ["YYY"]


def test_rows_without_a_name_are_excluded_from_players_imported():
    rows = [
        {"name": None, "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
        {"name": "A", "team": "NYY", "salary": 5000, "projection": 10.0, "position": "OF", "opponent": "BOS"},
    ]
    summary = build_validation_summary(rows, [], {"NYY", "BOS"})
    assert summary.players_imported == 1


def test_empty_rows_produce_zeroed_summary():
    summary = build_validation_summary([], [], set())
    assert summary.players_imported == 0
    assert summary.matched == 0
    assert summary.unknown_teams == []
