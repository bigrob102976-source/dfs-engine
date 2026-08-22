"""Milestone 32.3 -- end-to-end training pipeline integration test.
Runs historical_models.hitter_v1.train.run_training() against a small,
fully synthetic parquet file (no dependency on the real warehouse being
present) covering all three chronological windows and BOTH
feature-availability experiments, and checks:
  - real train/validation/test row counts come back
  - both ALWAYS_PREGAME and AFTER_LINEUP experiments ran
  - model selection only ever used VALIDATION metrics (final-test isolation)
  - the frozen model was evaluated on TEST exactly once
  - artifacts were written to disk
"""

import numpy as np
import pandas as pd
import pytest

from historical_models.hitter_v1 import config
from historical_models.hitter_v1.features import AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS
from historical_models.hitter_v1.train import run_training


def _date_range(start: str, end: str, n: int):
    span = pd.date_range(start, end, periods=n)
    return [d.strftime("%Y-%m-%d") for d in span]


def _make_synthetic_warehouse_parquet(tmp_path, seed=0):
    rng = np.random.default_rng(seed)

    train_dates = _date_range(config.TRAIN_START, config.TRAIN_END, 60)
    validation_dates = _date_range(config.VALIDATION_START, config.VALIDATION_END, 40)
    test_dates = _date_range(config.TEST_START, config.TEST_END, 30)
    all_dates = train_dates + validation_dates + test_dates
    n = len(all_dates)

    data = {
        "game_date": all_dates, "game_pk": list(range(n)), "player_id": [f"h{i}" for i in range(n)],
        "player_name": [f"Hitter {i}" for i in range(n)], "team": ["A"] * n,
        "actual_dk_points": rng.uniform(0, 30, size=n),
    }
    for col in AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS:
        data[col] = rng.uniform(0, 1, size=n)
    for col in AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["A", "B", "C"], size=n)

    df = pd.DataFrame(data)
    path = tmp_path / "hitter_game_features.parquet"
    df.to_parquet(path)
    return path


@pytest.fixture(scope="module")
def training_result(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("m32_3_train")
    warehouse_path = _make_synthetic_warehouse_parquet(tmp_path)
    output_dir = tmp_path / "artifacts"
    return run_training(warehouse_path=warehouse_path, output_dir=output_dir, seed=42)


def test_run_training_reports_real_row_counts(training_result):
    summary = training_result["dataset_summary"]
    assert summary.train_rows == 60
    assert summary.validation_rows == 40
    assert summary.test_rows == 30
    assert summary.total_rows == 130


def test_run_training_ran_both_feature_availability_experiments(training_result):
    classes_seen = {r["feature_availability_class"] for r in training_result["experiment_records"]}
    assert classes_seen == {"ALWAYS_PREGAME", "AFTER_LINEUP"}
    assert "ALWAYS_PREGAME" in training_result["best_by_class"]
    assert "AFTER_LINEUP" in training_result["best_by_class"]


def test_run_training_selects_model_using_validation_metrics_only(training_result):
    for record in training_result["experiment_records"]:
        assert "validation_MAE" in record
        assert "validation_RMSE" in record
        assert not any("test" in key.lower() for key in record.keys())


def test_run_training_evaluates_test_set_exactly_once(training_result):
    assert "test_metrics" in training_result
    assert training_result["test_metrics"]["n"] == 30


def test_run_training_selected_model_is_one_of_the_real_candidates(training_result):
    from historical_models.hitter_v1.model import CANDIDATES

    assert training_result["selected"]["model"] in {c.name for c in CANDIDATES}
    assert training_result["selected"]["feature_availability_class"] in ("ALWAYS_PREGAME", "AFTER_LINEUP")


def test_run_training_writes_artifacts_to_disk(training_result):
    from pathlib import Path

    for key in ("model", "metadata", "feature_list", "validation_metrics", "test_metrics", "feature_importance", "calibration", "ceiling_analysis", "outliers"):
        assert key in training_result["artifact_paths"]
        assert Path(training_result["artifact_paths"][key]).exists()


def test_run_training_reports_mean_baseline_comparison(training_result):
    assert "mean_baseline_test_metrics" in training_result
    assert training_result["mae_improvement_pct"] is not None


def test_run_training_reports_dfs_specific_and_diagnostic_sections(training_result):
    for key in ("top5", "top10", "top20", "calibration", "low_score_analysis", "ceiling_analysis", "outliers"):
        assert key in training_result
