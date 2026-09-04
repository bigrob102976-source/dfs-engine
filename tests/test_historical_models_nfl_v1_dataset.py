"""NFL M10 -- targeted tests for historical_models/nfl_v1/dataset.py."""

import pandas as pd

from historical_models.nfl_v1.config import SPLIT_TEST, SPLIT_TRAIN, SPLIT_VALIDATION
from historical_models.nfl_v1.dataset import add_recent_dk_points_feature, discover_feature_keys


def _df(rows):
    return pd.DataFrame(rows)


def test_discover_feature_keys_excludes_weeks_of_history():
    df = _df([{"rolling_features": {"carries_mean_last1": 5.0, "weeks_of_history": 3}, "season_to_date_features": {"carries_season_mean": 4.0}}])
    keys = discover_feature_keys(df)
    assert "carries_mean_last1" in keys
    assert "carries_season_mean" in keys
    assert "weeks_of_history" not in keys


def test_recent_dk_points_feature_is_leakage_safe():
    """Predicting week 6's recent-3-week baseline must use weeks 3-5's
    real target values, never week 6's own (even though it's present in
    the same combined frame the function reads from)."""
    splits = {
        SPLIT_TRAIN: _df([
            {"gsis_id": "00-1", "week": 3, "target_dk_points": 10.0},
            {"gsis_id": "00-1", "week": 4, "target_dk_points": 20.0},
            {"gsis_id": "00-1", "week": 5, "target_dk_points": 30.0},
        ]),
        SPLIT_VALIDATION: _df([{"gsis_id": "00-1", "week": 6, "target_dk_points": 999.0}]),
        SPLIT_TEST: _df([{"gsis_id": "00-1", "week": 7, "target_dk_points": 15.0}]),
    }
    out = add_recent_dk_points_feature(splits, id_col="gsis_id")
    val_row = out[SPLIT_VALIDATION].iloc[0]
    assert val_row["recent_dk_points_mean_last3"] == 20.0  # mean(10,20,30), never touches 999.0
