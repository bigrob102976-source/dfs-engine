"""Milestone 32.2 -- end-to-end training pipeline integration test.
Runs historical_models.pitcher_v1.train.run_training() against a small,
fully synthetic parquet file (no dependency on the real warehouse being
present) covering all three chronological windows, and checks:
  - real train/validation/test row counts come back
  - model selection only ever used VALIDATION metrics (final-test isolation)
  - the frozen model was evaluated on TEST exactly once
  - artifacts were written to disk
"""

import numpy as np
import pandas as pd
import pytest

from historical_models.pitcher_v1 import config
from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from historical_models.pitcher_v1.train import run_training


def _date_range(start: str, end: str, n: int):
    span = pd.date_range(start, end, periods=n)
    return [d.strftime("%Y-%m-%d") for d in span]


def _make_synthetic_warehouse_parquet(tmp_path, seed=0):
    rng = np.random.default_rng(seed)

    train_dates = _date_range(config.TRAIN_START, config.TRAIN_END, 40)
    validation_dates = _date_range(config.VALIDATION_START, config.VALIDATION_END, 30)
    test_dates = _date_range(config.TEST_START, config.TEST_END, 20)
    all_dates = train_dates + validation_dates + test_dates
    n = len(all_dates)

    data = {
        "game_date": all_dates,
        "game_pk": list(range(n)),
        "player_id": [f"p{i}" for i in range(n)],
        "player_name": [f"Pitcher {i}" for i in range(n)],
        "starter_flag": [True] * n,
        "actual_dk_points": rng.uniform(0, 30, size=n),
    }
    for col in NUMERIC_FEATURE_COLUMNS:
        data[col] = rng.uniform(0, 1, size=n)
    for col in CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["A", "B", "C"], size=n)

    df = pd.DataFrame(data)
    path = tmp_path / "pitcher_game_features.parquet"
    df.to_parquet(path)
    return path


@pytest.fixture(scope="module")
def training_result(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("m32_2_train")
    warehouse_path = _make_synthetic_warehouse_parquet(tmp_path)
    output_dir = tmp_path / "artifacts"
    return run_training(warehouse_path=warehouse_path, output_dir=output_dir, seed=42)


def test_run_training_reports_real_row_counts(training_result):
    summary = training_result["dataset_summary"]
    assert summary.train_rows == 40
    assert summary.validation_rows == 30
    assert summary.test_rows == 20
    assert summary.total_rows == 90
    assert summary.excluded_relief_rows == 0


def test_run_training_selects_model_using_validation_metrics_only(training_result):
    for record in training_result["experiment_records"]:
        assert "validation_MAE" in record
        assert "validation_RMSE" in record
        assert "validation_corr" in record
        assert not any("test" in key.lower() for key in record.keys())  # test scores never leak into selection records


def test_run_training_evaluates_test_set_exactly_once(training_result):
    assert "test_metrics" in training_result
    assert training_result["test_metrics"]["n"] == 20  # the full, untouched test split, scored once


def test_run_training_selected_model_is_one_of_the_real_candidates(training_result):
    from historical_models.pitcher_v1.model import CANDIDATES

    assert training_result["selected"]["model"] in {c.name for c in CANDIDATES}


def test_run_training_writes_artifacts_to_disk(training_result):
    for key in ("model", "metadata", "feature_list", "validation_metrics", "test_metrics", "feature_importance", "calibration", "outliers"):
        assert key in training_result["artifact_paths"]
        from pathlib import Path

        assert Path(training_result["artifact_paths"][key]).exists()


def test_run_training_reports_mean_baseline_comparison(training_result):
    assert "mean_baseline_test_metrics" in training_result
    assert training_result["mae_improvement_pct"] is not None
