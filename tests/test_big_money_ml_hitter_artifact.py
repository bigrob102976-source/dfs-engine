"""Milestone 32.3B -- frozen HITTER model artifact loading + fail-closed
validation tests. No network calls; uses tmp_path fixtures only.
Mirrors tests/test_big_money_ml_artifact.py exactly, but also covers
the hitter-specific feature_availability_class validation (which the
pitcher artifact does not have, since pitcher_v1 uses a single fixed
FEATURE_COLUMNS list)."""

import numpy as np
import pandas as pd
import pytest

from big_money_ml.hitter_artifact import HitterModelArtifactError, load_and_validate_frozen_hitter_model
from historical_models.hitter_v1.features import AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS, AFTER_LINEUP_FEATURE_COLUMNS, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS
from historical_models.hitter_v1.metadata import ModelMetadata
from historical_models.hitter_v1.model import CANDIDATES, build_pipeline
from historical_models.hitter_v1.persistence import save_all_artifacts


def _tiny_fitted_pipeline():
    rng = np.random.default_rng(0)
    n = 20
    data = {col: rng.uniform(0, 1, size=n) for col in AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS}
    for col in AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["A", "B"], size=n)
    X = pd.DataFrame(data)
    y = pd.Series(rng.uniform(0, 30, size=n))
    spec = next(c for c in CANDIDATES if c.name == "ridge")
    pipeline = build_pipeline(spec, {"alpha": 1.0}, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS, AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS)
    pipeline.fit(X, y)
    return pipeline


def _write_valid_artifact(tmp_path, model_version="1.0.0", feature_availability_class="AFTER_LINEUP", feature_list=None):
    pipeline = _tiny_fitted_pipeline()
    feature_list = AFTER_LINEUP_FEATURE_COLUMNS if feature_list is None else feature_list
    metadata = ModelMetadata(
        feature_availability_class=feature_availability_class, feature_list=feature_list,
        model_type="ridge", hyperparameters={"alpha": 1.0}, seed=42,
    ).to_dict()
    metadata["model_version"] = model_version
    save_all_artifacts(tmp_path, pipeline, metadata, feature_list, validation_metrics={"mae": 5.0})
    return tmp_path


def test_load_and_validate_frozen_hitter_model_succeeds_on_a_valid_artifact(tmp_path):
    _write_valid_artifact(tmp_path)
    frozen = load_and_validate_frozen_hitter_model(tmp_path)
    assert frozen.model_version == "1.0.0"
    assert frozen.feature_availability_class == "AFTER_LINEUP"
    assert frozen.feature_list == AFTER_LINEUP_FEATURE_COLUMNS
    assert frozen.pipeline is not None


def test_load_and_validate_frozen_hitter_model_raises_on_missing_directory(tmp_path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(HitterModelArtifactError):
        load_and_validate_frozen_hitter_model(missing)


def test_load_and_validate_frozen_hitter_model_fails_closed_on_version_mismatch(tmp_path):
    _write_valid_artifact(tmp_path, model_version="0.9.0")
    with pytest.raises(HitterModelArtifactError, match="model_version"):
        load_and_validate_frozen_hitter_model(tmp_path)


def test_load_and_validate_frozen_hitter_model_fails_closed_on_feature_schema_mismatch(tmp_path):
    _write_valid_artifact(tmp_path, feature_list=AFTER_LINEUP_FEATURE_COLUMNS[:-1])  # one feature short
    with pytest.raises(HitterModelArtifactError, match="feature"):
        load_and_validate_frozen_hitter_model(tmp_path)


def test_load_and_validate_frozen_hitter_model_fails_closed_on_reordered_feature_schema(tmp_path):
    reordered = list(reversed(AFTER_LINEUP_FEATURE_COLUMNS))
    _write_valid_artifact(tmp_path, feature_list=reordered)
    with pytest.raises(HitterModelArtifactError):
        load_and_validate_frozen_hitter_model(tmp_path)


def test_load_and_validate_frozen_hitter_model_fails_closed_on_unrecognized_availability_class(tmp_path):
    _write_valid_artifact(tmp_path, feature_availability_class="SOMETHING_ELSE")
    with pytest.raises(HitterModelArtifactError, match="feature_availability_class"):
        load_and_validate_frozen_hitter_model(tmp_path)


def test_load_and_validate_frozen_hitter_model_rejects_always_pregame_class_when_features_are_after_lineup(tmp_path):
    """The artifact declares ALWAYS_PREGAME but its actual feature_list
    is the (longer) AFTER_LINEUP set -- a corrupted/mismatched artifact
    must fail closed, never silently run against the wrong schema."""
    _write_valid_artifact(tmp_path, feature_availability_class="ALWAYS_PREGAME", feature_list=AFTER_LINEUP_FEATURE_COLUMNS)
    with pytest.raises(HitterModelArtifactError):
        load_and_validate_frozen_hitter_model(tmp_path)
