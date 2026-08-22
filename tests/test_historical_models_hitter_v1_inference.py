"""Milestone 32.3 -- predict_hitter() inference-interface schema tests.
Trains a tiny throwaway pipeline, saves it under tmp_path, and confirms
the clean inference contract: projection, model_version,
feature_availability_class, feature_coverage, missing_features,
data_quality_score."""

import numpy as np
import pandas as pd
import pytest

from historical_models.hitter_v1.features import AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS, AFTER_LINEUP_FEATURE_COLUMNS, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS
from historical_models.hitter_v1.inference import HitterModelPrediction, predict_hitter
from historical_models.hitter_v1.metadata import ModelMetadata
from historical_models.hitter_v1.model import CANDIDATES, build_pipeline
from historical_models.hitter_v1.persistence import save_all_artifacts


@pytest.fixture()
def trained_artifact_dir(tmp_path):
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

    metadata = ModelMetadata(
        feature_availability_class="AFTER_LINEUP", feature_list=AFTER_LINEUP_FEATURE_COLUMNS,
        model_type="ridge", hyperparameters={"alpha": 1.0}, seed=42,
    ).to_dict()
    save_all_artifacts(tmp_path, pipeline, metadata, AFTER_LINEUP_FEATURE_COLUMNS, validation_metrics={"mae": 5.0})

    return tmp_path, X


def test_predict_hitter_returns_full_schema(trained_artifact_dir):
    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()
    features["player_id"] = "12345"

    result = predict_hitter(features, artifact_dir=artifact_dir)

    assert isinstance(result, HitterModelPrediction)
    assert result.player_id == "12345"
    assert isinstance(result.projection, float)
    assert result.model_version == "1.0.0"
    assert result.feature_availability_class == "AFTER_LINEUP"
    assert result.feature_coverage == 1.0
    assert result.missing_features == []
    assert 0.0 <= result.data_quality_score <= 1.0


def test_predict_hitter_reports_missing_features_when_keys_absent(trained_artifact_dir):
    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()
    del features[AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS[0]]
    del features[AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS[1]]

    result = predict_hitter(features, artifact_dir=artifact_dir)

    assert AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS[0] in result.missing_features
    assert AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS[1] in result.missing_features
    assert result.feature_coverage < 1.0
    assert result.data_quality_score < 1.0


def test_predict_hitter_rejects_leaked_columns_in_input(trained_artifact_dir):
    artifact_dir, X = trained_artifact_dir
    features = X.iloc[0].to_dict()
    features["actual_dk_points"] = 25.0

    with pytest.raises(ValueError):
        predict_hitter(features, artifact_dir=artifact_dir)


def test_predict_hitter_allows_but_ignores_player_identity_in_input(trained_artifact_dir):
    """Identity fields may be passed for joining/evaluation/reporting
    (per the milestone's explicit "PLAYER IDENTITY" instruction) -- must
    never raise, and must never influence the projection."""
    artifact_dir, X = trained_artifact_dir
    features_with_id = X.iloc[0].to_dict()
    features_with_id["player_id"] = "12345"
    features_with_id["opposing_starting_pitcher_id"] = "999"
    features_without_id = X.iloc[0].to_dict()

    result_with = predict_hitter(features_with_id, artifact_dir=artifact_dir)
    result_without = predict_hitter(features_without_id, artifact_dir=artifact_dir)
    assert result_with.projection == result_without.projection


def test_predict_hitter_never_returns_confidence_field():
    """Explicit instruction: use DATA QUALITY, not statistical
    'confidence' unless genuinely calibrated -- the schema uses
    data_quality_score instead, never a field literally named 'confidence'."""
    field_names = set(HitterModelPrediction.__dataclass_fields__.keys())
    assert "confidence" not in field_names
    assert "data_quality_score" in field_names


def test_predict_hitter_raises_clearly_when_no_artifact_exists(tmp_path):
    with pytest.raises(FileNotFoundError):
        predict_hitter({"player_id": "1"}, artifact_dir=tmp_path)
