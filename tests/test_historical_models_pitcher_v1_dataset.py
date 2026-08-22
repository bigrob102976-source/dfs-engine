"""Milestone 32.2 -- dataset loading / starting-pitcher filter /
chronological split tests for historical_models.pitcher_v1.dataset.
Synthetic DataFrames only -- no dependency on the real warehouse file
being present."""

import numpy as np
import pandas as pd
import pytest

from historical_models.pitcher_v1 import config
from historical_models.pitcher_v1.dataset import build_dataset_summary, chronological_split, get_target, missingness_by_family
from historical_models.pitcher_v1.features import FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS


def _synthetic_pitcher_df(dates, starter_flags=None, seed=0):
    n = len(dates)
    rng = np.random.default_rng(seed)
    starter_flags = starter_flags if starter_flags is not None else [True] * n
    data = {
        "game_date": dates,
        "game_pk": list(range(1000, 1000 + n)),
        "player_id": [f"p{i}" for i in range(n)],
        "player_name": [f"Pitcher {i}" for i in range(n)],
        "starter_flag": starter_flags,
        "actual_dk_points": rng.uniform(0, 30, size=n),
    }
    for col in NUMERIC_FEATURE_COLUMNS:
        data[col] = rng.uniform(0, 1, size=n)
    for col in ("team", "opponent", "home_away", "throw_hand", "bat_hand", "venue_roof_type", "venue_id"):
        data[col] = ["A"] * n
    return pd.DataFrame(data)


def test_chronological_split_partitions_every_row_exactly_once():
    dates = ["2024-04-01"] * 3 + ["2025-07-15"] * 2 + ["2025-09-10"] * 4
    df = _synthetic_pitcher_df(dates)
    train, validation, test = chronological_split(df)
    assert len(train) == 3
    assert len(validation) == 2
    assert len(test) == 4


def test_chronological_split_raises_loudly_on_dates_outside_every_window():
    """Rows outside all three configured windows must never be silently
    dropped -- the split asserts a full partition, per CLAUDE.md's 'fail
    loudly when critical data is missing.'"""
    dates = ["2024-04-01", "2023-01-01", "2026-01-01"]  # the latter two fall outside train/validation/test entirely
    df = _synthetic_pitcher_df(dates)
    with pytest.raises(AssertionError):
        chronological_split(df)


def test_chronological_split_has_no_date_overlap_between_splits():
    dates = ["2024-04-01", "2025-07-01", "2025-07-15", "2025-08-31", "2025-09-01", "2025-09-28"]
    df = _synthetic_pitcher_df(dates)
    train, validation, test = chronological_split(df)
    assert train["game_date"].max() < validation["game_date"].min()
    assert validation["game_date"].max() < test["game_date"].min()
    assert train["game_date"].max() <= config.TRAIN_END
    assert validation["game_date"].min() >= config.VALIDATION_START
    assert validation["game_date"].max() <= config.VALIDATION_END
    assert test["game_date"].min() >= config.TEST_START


def test_chronological_split_asserts_on_gap_free_partition_of_only_in_range_rows():
    dates = ["2024-04-01", "2025-07-15", "2025-09-10"]
    df = _synthetic_pitcher_df(dates)
    train, validation, test = chronological_split(df)
    assert len(train) + len(validation) + len(test) == len(df)


def test_build_dataset_summary_reports_excluded_relief_rows():
    all_rows = _synthetic_pitcher_df(["2024-04-01"] * 5, starter_flags=[True, True, False, False, False])
    starters = all_rows[all_rows["starter_flag"] == True].reset_index(drop=True)  # noqa: E712
    train, validation, test = chronological_split(starters)
    summary = build_dataset_summary(all_rows, starters, train, validation, test)
    assert summary.total_rows == 5
    assert summary.retained_starter_rows == 2
    assert summary.excluded_relief_rows == 3


def test_get_target_returns_actual_dk_points():
    df = _synthetic_pitcher_df(["2024-04-01", "2024-04-02"])
    target = get_target(df)
    assert target.name == "actual_dk_points"
    assert len(target) == 2


def test_missingness_by_family_reflects_injected_nans():
    df = _synthetic_pitcher_df(["2024-04-01"] * 20)
    rolling_col = next(c for c in FEATURE_COLUMNS if c.startswith("rolling_"))
    df.loc[: len(df) // 2 - 1, rolling_col] = np.nan  # exactly half missing
    result = missingness_by_family(df)
    assert "rolling" in result
    assert result["rolling"] > 0
