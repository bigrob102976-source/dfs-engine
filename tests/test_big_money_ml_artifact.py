"""Milestone 32.2B -- frozen model artifact loading + fail-closed
validation tests. No network calls; uses tmp_path fixtures only."""

import numpy as np
import pandas as pd
import pytest

from big_money_ml.artifact import ModelArtifactError, load_and_validate_frozen_pitcher_model
from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from historical_models.pitcher_v1.metadata import ModelMetadata
from historical_models.pitcher_v1.model import CANDIDATES, build_pipeline
from historical_models.pitcher_v1.persistence import save_all_artifacts


def _tiny_fitted_pipeline():
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
    return pipeline


def _write_valid_artifact(tmp_path, model_version="1.0.0", feature_list=None):
    pipeline = _tiny_fitted_pipeline()
    feature_list = FEATURE_COLUMNS if feature_list is None else feature_list
    metadata = ModelMetadata(feature_list=feature_list, model_type="ridge", hyperparameters={"alpha": 1.0}, seed=42).to_dict()
    metadata["model_version"] = model_version
    save_all_artifacts(tmp_path, pipeline, metadata, feature_list, validation_metrics={"mae": 5.0})
    return tmp_path


def test_load_and_validate_frozen_pitcher_model_succeeds_on_a_valid_artifact(tmp_path):
    _write_valid_artifact(tmp_path)
    frozen = load_and_validate_frozen_pitcher_model(tmp_path)
    assert frozen.model_version == "1.0.0"
    assert frozen.feature_list == FEATURE_COLUMNS
    assert frozen.pipeline is not None


def test_load_and_validate_frozen_pitcher_model_raises_on_missing_directory(tmp_path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ModelArtifactError):
        load_and_validate_frozen_pitcher_model(missing)


def test_load_and_validate_frozen_pitcher_model_fails_closed_on_version_mismatch(tmp_path):
    _write_valid_artifact(tmp_path, model_version="0.9.0")
    with pytest.raises(ModelArtifactError, match="model_version"):
        load_and_validate_frozen_pitcher_model(tmp_path)


def test_load_and_validate_frozen_pitcher_model_fails_closed_on_feature_schema_mismatch(tmp_path):
    _write_valid_artifact(tmp_path, feature_list=FEATURE_COLUMNS[:-1])  # one feature short
    with pytest.raises(ModelArtifactError, match="feature"):
        load_and_validate_frozen_pitcher_model(tmp_path)


def test_load_and_validate_frozen_pitcher_model_fails_closed_on_reordered_feature_schema(tmp_path):
    reordered = list(reversed(FEATURE_COLUMNS))
    _write_valid_artifact(tmp_path, feature_list=reordered)
    with pytest.raises(ModelArtifactError):
        load_and_validate_frozen_pitcher_model(tmp_path)
