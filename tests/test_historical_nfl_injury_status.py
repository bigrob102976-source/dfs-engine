"""NFL M9 -- targeted tests for historical_nfl/injury_status.py."""

from historical_nfl.injury_status import build_injury_status_lookup


def test_lookup_scoped_to_exact_week():
    rows = [
        {"week": 1, "gsis_id": "00-1", "report_status": "Questionable"},
        {"week": 2, "gsis_id": "00-1", "report_status": "Out"},
    ]
    lookup = build_injury_status_lookup(rows, week=2)
    assert lookup["00-1"] == "Out"


def test_no_stale_carryforward_from_prior_week():
    rows = [{"week": 1, "gsis_id": "00-1", "report_status": "Out"}]
    lookup = build_injury_status_lookup(rows, week=2)
    assert "00-1" not in lookup  # never carried forward


def test_player_absent_from_report_has_no_entry():
    rows = [{"week": 1, "gsis_id": "00-2", "report_status": "Out"}]
    lookup = build_injury_status_lookup(rows, week=1)
    assert "00-1" not in lookup
