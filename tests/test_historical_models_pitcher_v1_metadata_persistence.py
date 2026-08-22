"""Milestone 32.2 -- ModelMetadata shape + artifact save/load round-trip
tests for historical_models.pitcher_v1.metadata/persistence."""

import json

import joblib
import pandas as pd

from historical_models.pitcher_v1.metadata import ModelMetadata
from historical_models.pitcher_v1.model import CANDIDATES, build_pipeline
from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from historical_models.pitcher_v1.persistence import (
    append_experiment_record,
    load_json,
    load_model,
    save_all_artifacts,
    save_model,
)


def test_model_metadata_to_dict_contains_every_required_field():
    metadata = ModelMetadata(feature_list=["a", "b"], model_type="ridge", hyperparameters={"alpha": 1.0}, seed=42)
    d = metadata.to_dict()
    for field in (
        "model_version", "warehouse_version", "target_column", "train_date_range", "validation_date_range",
        "test_date_range", "feature_list", "model_type", "hyperparameters", "seed", "library_versions",
        "git_commit", "training_timestamp", "salary_used_as_feature", "vegas_used_as_feature",
    ):
        assert field in d


def test_model_metadata_never_declares_salary_or_vegas_as_features():
    metadata = ModelMetadata(feature_list=["a"], model_type="ridge", hyperparameters={}, seed=1)
    assert metadata.salary_used_as_feature is False
    assert metadata.vegas_used_as_feature is False


def test_model_metadata_target_column_is_actual_dk_points():
    metadata = ModelMetadata(feature_list=[], model_type="mean_baseline", hyperparameters={}, seed=1)
    assert metadata.target_column == "actual_dk_points"


def test_save_json_and_load_json_round_trip(tmp_path):
    payload = {"mae": 5.5, "nested": {"x": [1, 2, 3]}}
    from historical_models.pitcher_v1.persistence import save_json

    save_json(tmp_path, "example.json", payload)
    loaded = load_json(tmp_path, "example.json")
    assert loaded == payload


def test_load_json_returns_none_for_missing_file(tmp_path):
    assert load_json(tmp_path, "does_not_exist.json") is None


def _tiny_fitted_pipeline():
    import numpy as np

    rng = np.random.default_rng(0)
    n = 20
    data = {col: rng.uniform(0, 1, size=n) for col in NUMERIC_FEATURE_COLUMNS}
    for col in CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["A", "B"], size=n)
    X = pd.DataFrame(data)
    y = pd.Series(rng.uniform(0, 30, size=n))
    spec = next(c for c in CANDIDATES if c.name == "ridge")
    pipeline = build_pipeline(spec, {"alpha": 1.0})
    pipeline.fit(X, y)
    return pipeline, X


def test_save_model_and_load_model_round_trip_predictions_match(tmp_path):
    pipeline, X = _tiny_fitted_pipeline()
    save_model(tmp_path, pipeline)
    reloaded = load_model(tmp_path)
    assert (reloaded.predict(X) == pipeline.predict(X)).all()


def test_append_experiment_record_is_append_only_never_overwrites(tmp_path):
    append_experiment_record(tmp_path, {"experiment_id": "exp1", "validation_MAE": 5.0})
    append_experiment_record(tmp_path, {"experiment_id": "exp2", "validation_MAE": 4.5})
    lines = (tmp_path / "experiments.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert records[0]["experiment_id"] == "exp1"
    assert records[1]["experiment_id"] == "exp2"


def test_save_all_artifacts_writes_every_declared_file(tmp_path):
    pipeline, _ = _tiny_fitted_pipeline()
    metadata = ModelMetadata(feature_list=["a"], model_type="ridge", hyperparameters={"alpha": 1.0}, seed=42).to_dict()
    paths = save_all_artifacts(
        tmp_path, pipeline, metadata, ["a", "b"],
        validation_metrics={"mae": 5.0}, test_metrics={"mae": 5.5},
        feature_importance=[{"feature": "a", "importance_mean": 0.1}],
        calibration=[{"bucket": "5-10", "count": 3}],
        outliers={"largest_over_projections": [], "largest_under_projections": []},
    )
    for key in ("model", "metadata", "feature_list", "validation_metrics", "test_metrics", "feature_importance", "calibration", "outliers"):
        assert key in paths
        assert paths[key].exists()
