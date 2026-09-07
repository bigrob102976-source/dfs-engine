"""NFL M9 -- targeted tests for historical_nfl/dst_rolling.py, mirroring
tests/test_historical_nfl_usage_rolling.py's leakage-focused style."""

from historical_nfl.dst_usage_models import NflDstUsageRecord
from historical_nfl.dst_rolling import compute_dst_rolling_features

TEAM = "PHI"


def _record(week, sacks=None):
    return NflDstUsageRecord(team=TEAM, opponent="DAL", season=2025, week=week, game_id=f"g{week}", sacks=sacks)


def test_leakage_as_of_week_never_includes_that_weeks_own_record():
    records = [_record(w, sacks=w * 1.0) for w in range(1, 8)]  # week 5 has sacks=5.0
    features = compute_dst_rolling_features(records, TEAM, as_of_week=5, windows=(1,))
    assert features["sacks_mean_last1"] == 4.0  # week 4's value, never week 5's


def test_no_history_returns_none():
    features = compute_dst_rolling_features([], TEAM, as_of_week=1, windows=(1, 3))
    assert features["sacks_mean_last1"] is None
    assert features["weeks_of_history"] == 0


def test_different_team_never_mixed():
    records = [_record(1, sacks=1.0), NflDstUsageRecord(team="DAL", opponent="PHI", season=2025, week=1, game_id="g1", sacks=99.0)]
    features = compute_dst_rolling_features(records, TEAM, as_of_week=2, windows=(1,))
    assert features["sacks_mean_last1"] == 1.0
