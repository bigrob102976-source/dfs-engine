"""NFL M8 -- targeted tests for historical_nfl/usage_rolling.py, with
strong emphasis on the leakage-prevention invariant (a Week W feature
must never read Week W or later)."""

from historical_nfl.usage_models import NflUsageRecord
from historical_nfl.usage_rolling import compute_player_rolling_features, compute_season_to_date_features

GSIS = "00-1"


def _record(week, targets=None, target_share=None, passing_yards=None):
    return NflUsageRecord(
        canonical_player_id=f"gsis:{GSIS}", gsis_id=GSIS, season=2025, week=week, game_id=f"g{week}",
        team="PHI", opponent="DAL", position="WR",
        targets=targets, target_share=target_share, passing_yards=passing_yards,
    )


def test_leakage_as_of_week_never_includes_that_weeks_own_record():
    """The core invariant: even though week 5's record IS in the input
    list, computing as_of_week=5 must never read it."""
    records = [_record(w, targets=w * 10) for w in range(1, 8)]  # weeks 1-7, week 5 has targets=50
    features = compute_player_rolling_features(records, GSIS, as_of_week=5, windows=(1,))
    # last-1-week (window=1) as of week 5 should be week 4's value (40), never week 5's (50)
    assert features["targets_mean_last1"] == 40.0
    assert features["targets_sum_last1"] == 40.0


def test_leakage_never_includes_future_weeks_either():
    records = [_record(w, targets=w * 10) for w in range(1, 10)]  # includes weeks 6-9, all "future" relative to week 5
    features = compute_player_rolling_features(records, GSIS, as_of_week=5, windows=(5,))
    # mean of weeks 1-4 (targets 10,20,30,40) -- must NOT include weeks 5-9
    assert features["targets_mean_last5"] == 25.0
    assert features["targets_sum_last5"] == 100.0


def test_season_to_date_leakage_boundary():
    records = [_record(w, targets=w) for w in range(1, 10)]
    features = compute_season_to_date_features(records, GSIS, as_of_week=6)
    # weeks 1-5 only (1+2+3+4+5=15), never week 6+
    assert features["targets_season_sum"] == 15.0
    assert features["targets_season_mean"] == 3.0
    assert features["season_weeks_of_history"] == 5


def test_no_history_returns_none_not_zero():
    records = [_record(1, targets=5)]
    features = compute_player_rolling_features(records, GSIS, as_of_week=1, windows=(1, 3, 5))
    assert features["targets_mean_last1"] is None
    assert features["targets_mean_last3"] is None
    assert features["weeks_of_history"] == 0


def test_partial_window_uses_only_real_available_weeks():
    """Week 3, window=5 -- only weeks 1-2 exist; must average just those
    two, never treat missing weeks as zero."""
    records = [_record(1, targets=10), _record(2, targets=20)]
    features = compute_player_rolling_features(records, GSIS, as_of_week=3, windows=(5,))
    assert features["targets_mean_last5"] == 15.0
    assert features["targets_sum_last5"] == 30.0


def test_share_fields_get_mean_only_no_sum_key():
    records = [_record(1, target_share=0.3), _record(2, target_share=0.5)]
    features = compute_player_rolling_features(records, GSIS, as_of_week=3, windows=(3,))
    assert features["target_share_mean_last3"] == 0.4
    assert "target_share_sum_last3" not in features


def test_missing_field_within_window_excluded_not_treated_as_zero():
    records = [_record(1, targets=10), _record(2, targets=None), _record(3, targets=30)]
    features = compute_player_rolling_features(records, GSIS, as_of_week=4, windows=(3,))
    # week 2's None must be skipped, not counted as 0 -- mean of [10, 30] = 20, not (10+0+30)/3
    assert features["targets_mean_last3"] == 20.0
    assert features["targets_sum_last3"] == 40.0


def test_trend_delta_compares_last_real_week_to_prior_history():
    records = [_record(1, targets=10), _record(2, targets=10), _record(3, targets=20)]
    features = compute_player_rolling_features(records, GSIS, as_of_week=4)
    # last real week (3) has 20; prior weeks (1,2) mean 10 -> delta +10
    assert features["targets_trend_delta"] == 10.0


def test_trend_delta_none_with_only_one_week_of_history():
    records = [_record(1, targets=10)]
    features = compute_player_rolling_features(records, GSIS, as_of_week=2)
    assert features["targets_trend_delta"] is None


def test_different_player_ids_never_mixed():
    records = [
        _record(1, targets=10),
        NflUsageRecord(canonical_player_id="gsis:00-2", gsis_id="00-2", season=2025, week=1, game_id="g1", team="DAL", opponent="PHI", position="WR", targets=999),
    ]
    features = compute_player_rolling_features(records, GSIS, as_of_week=2, windows=(1,))
    assert features["targets_mean_last1"] == 10.0  # never the other player's 999
