"""Milestone 32.2 -- predict_pitcher() inference-interface schema tests.
Trains a tiny throwaway pipeline, saves it under tmp_path, and confirms
the clean inference contract: projection, model_version,
feature_coverage, missing_features, data_quality_score."""

import numpy as np
import pandas as pd
import pytest

from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from historical_models.pitcher_v1.inference import PitcherModelPrediction, predict_pitcher
from historical_models.pitcher_v1.metadata import ModelMetadata
from historical_models.pitcher_v1.model import CANDIDATES, build_pipeline
from historical_models.pitcher_v1.persistence import save_all_artifacts


@pytest.fixture()
def trained_artifact_dir(tmp_path):
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

    metadata = ModelMetadata(feature_list=FEATURE_COLUMNS, model_type="ridge", hyperparameters={"alpha": 1.0}, seed=42).to_dict()
    save_all_artifacts(tmp_path, pipeline, metadata, FEATURE_COLUMNS, validation_metrics={"mae": 5.0})

    return tmp_path, X


def test_predict_pitcher_returns_full_schema(trained_artifact_dir):
    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()
    features["player_id"] = "12345"

    result = predict_pitcher(features, artifact_dir=artifact_dir)

    assert isinstance(result, PitcherModelPrediction)
    assert result.player_id == "12345"
    assert isinstance(result.projection, float)
    assert result.model_version == "1.0.0"
    assert result.feature_coverage == 1.0
    assert result.missing_features == []
    assert 0.0 <= result.data_quality_score <= 1.0


def test_predict_pitcher_reports_missing_features_when_keys_absent(trained_artifact_dir):
    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()
    del features[NUMERIC_FEATURE_COLUMNS[0]]
    del features[NUMERIC_FEATURE_COLUMNS[1]]

    result = predict_pitcher(features, artifact_dir=artifact_dir)

    assert NUMERIC_FEATURE_COLUMNS[0] in result.missing_features
    assert NUMERIC_FEATURE_COLUMNS[1] in result.missing_features
    assert result.feature_coverage < 1.0
    assert result.data_quality_score < 1.0


def test_predict_pitcher_rejects_leaked_columns_in_input(trained_artifact_dir):
    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()
    features["actual_dk_points"] = 25.0  # simulates a caller accidentally passing the outcome back in

    with pytest.raises(ValueError):
        predict_pitcher(features, artifact_dir=artifact_dir)


def test_predict_pitcher_never_returns_confidence_field():
    """Explicit instruction: don't invent 'confidence = 100' -- the
    inference schema uses data_quality_score instead, never a field
    literally named 'confidence'."""
    assert not hasattr(PitcherModelPrediction, "confidence")
    field_names = set(PitcherModelPrediction.__dataclass_fields__.keys())
    assert "confidence" not in field_names
    assert "data_quality_score" in field_names


def test_predict_pitcher_with_preloaded_pipeline_is_numerically_equivalent_to_fresh_load(trained_artifact_dir):
    """Milestone 32.4 performance optimization -- passing an
    already-loaded pipeline/metadata must produce a BYTE-IDENTICAL
    projection to the fresh-load-every-call path, never a different
    prediction."""
    from historical_models.pitcher_v1.persistence import METADATA_FILENAME, load_json, load_model

    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()
    features["player_id"] = "12345"

    fresh = predict_pitcher(features, artifact_dir=artifact_dir)

    pipeline = load_model(artifact_dir)
    metadata = load_json(artifact_dir, METADATA_FILENAME)
    preloaded = predict_pitcher(features, artifact_dir=artifact_dir, pipeline=pipeline, metadata=metadata)

    assert preloaded.projection == fresh.projection
    assert preloaded.model_version == fresh.model_version
    assert preloaded.feature_coverage == fresh.feature_coverage
    assert preloaded.data_quality_score == fresh.data_quality_score


def test_predict_pitcher_never_reloads_model_when_pipeline_is_preloaded(trained_artifact_dir, monkeypatch):
    """Proves the performance fix actually skips the disk read -- not
    just that output happens to match."""
    import historical_models.pitcher_v1.inference as inference_module

    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()

    def _boom(_artifact_dir):
        raise AssertionError("load_model must not be called when a pipeline is already supplied")

    pipeline = inference_module.load_model(artifact_dir)
    metadata = inference_module.load_json(artifact_dir, inference_module.METADATA_FILENAME)
    monkeypatch.setattr(inference_module, "load_model", _boom)

    result = predict_pitcher(features, artifact_dir=artifact_dir, pipeline=pipeline, metadata=metadata)
    assert isinstance(result, PitcherModelPrediction)
