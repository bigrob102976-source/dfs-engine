"""Milestone 32.3 -- dataset loading / chronological split / hitter-only
filtering tests for historical_models.hitter_v1.dataset. Synthetic
DataFrames only -- no dependency on the real warehouse file."""

import numpy as np
import pandas as pd
import pytest

from historical_models.hitter_v1 import config
from historical_models.hitter_v1.dataset import (
    build_dataset_summary, chronological_split, get_target, missingness_by_family, target_distribution_summary,
)
from historical_models.hitter_v1.features import ALWAYS_PREGAME_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS


def _synthetic_hitter_df(dates, seed=0):
    n = len(dates)
    rng = np.random.default_rng(seed)
    data = {
        "game_date": dates, "game_pk": list(range(1000, 1000 + n)), "player_id": [f"h{i}" for i in range(n)],
        "player_name": [f"Hitter {i}" for i in range(n)], "actual_dk_points": rng.uniform(0, 30, size=n),
        "team": ["A"] * n,
    }
    for col in NUMERIC_FEATURE_COLUMNS:
        data[col] = rng.uniform(0, 1, size=n)
    for col in ("opponent", "home_away", "bat_hand", "throw_hand", "venue_roof_type", "venue_id"):
        data[col] = ["X"] * n
    return pd.DataFrame(data)


def test_chronological_split_partitions_every_row_exactly_once():
    dates = ["2024-04-01"] * 3 + ["2025-07-15"] * 2 + ["2025-09-10"] * 4
    df = _synthetic_hitter_df(dates)
    train, validation, test = chronological_split(df)
    assert len(train) == 3
    assert len(validation) == 2
    assert len(test) == 4


def test_chronological_split_raises_loudly_on_dates_outside_every_window():
    dates = ["2024-04-01", "2023-01-01", "2026-01-01"]
    df = _synthetic_hitter_df(dates)
    with pytest.raises(AssertionError):
        chronological_split(df)


def test_chronological_split_has_no_date_overlap_between_splits():
    dates = ["2024-04-01", "2025-07-01", "2025-07-15", "2025-08-31", "2025-09-01", "2025-09-28"]
    df = _synthetic_hitter_df(dates)
    train, validation, test = chronological_split(df)
    assert train["game_date"].max() < validation["game_date"].min()
    assert validation["game_date"].max() < test["game_date"].min()
    assert train["game_date"].max() <= config.TRAIN_END
    assert validation["game_date"].min() >= config.VALIDATION_START
    assert test["game_date"].min() >= config.TEST_START


def test_build_dataset_summary_reports_unique_counts():
    dates = ["2024-04-01"] * 5
    df = _synthetic_hitter_df(dates)
    train, validation, test = chronological_split(df)
    summary = build_dataset_summary(df, train, validation, test)
    assert summary.total_rows == 5
    assert summary.unique_hitters == 5
    assert summary.unique_games == 5
    assert summary.unique_teams == 1


def test_get_target_returns_actual_dk_points():
    df = _synthetic_hitter_df(["2024-04-01", "2024-04-02"])
    target = get_target(df)
    assert target.name == "actual_dk_points"
    assert len(target) == 2


def test_missingness_by_family_reflects_injected_nans():
    df = _synthetic_hitter_df(["2024-04-01"] * 20)
    rolling_col = next(c for c in ALWAYS_PREGAME_FEATURE_COLUMNS if c.startswith("rolling_"))
    df.loc[: len(df) // 2 - 1, rolling_col] = np.nan
    result = missingness_by_family(df, ALWAYS_PREGAME_FEATURE_COLUMNS)
    assert "rolling" in result
    assert result["rolling"] > 0


def test_target_distribution_summary_reports_expected_keys():
    df = _synthetic_hitter_df(["2024-04-01"] * 50)
    dist = target_distribution_summary(df)
    for key in ("mean", "median", "std", "min", "max", "p10", "p25", "p50", "p75", "p90", "p95", "p99"):
        assert key in dist


def test_target_distribution_reflects_noisy_hitter_shape():
    """A realistic hitter target distribution: heavy at/near zero,
    right-skewed -- P10/P25 near 0, mean well above median."""
    rng = np.random.default_rng(1)
    n = 2000
    zeros = np.zeros(int(n * 0.3))
    rest = rng.exponential(scale=5, size=n - len(zeros))
    values = np.concatenate([zeros, rest])
    df = pd.DataFrame({"actual_dk_points": values})
    dist = target_distribution_summary(df)
    assert dist["p10"] == 0.0
    assert dist["mean"] > dist["median"]
