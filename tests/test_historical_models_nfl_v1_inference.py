"""NFL M10 -- targeted tests for historical_models/nfl_v1/inference.py.
Strict artifact validation is the core of this file's coverage."""

import pytest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

from historical_models.nfl_v1.config import MODEL_VERSION, TARGET_SCORING_VERSION
from historical_models.nfl_v1.inference import NflModelArtifactError, load_position_model, predict_one
from historical_models.nfl_v1.persistence import save_all_artifacts


def _real_pipeline():
    """A genuinely fit sklearn Pipeline (imputer + Ridge), not a mock --
    predict() must actually work on it."""
    import numpy as np
    pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", Ridge())])
    X = np.array([[1.0, 2.0], [2.0, 3.0], [3.0, np.nan], [4.0, 5.0]])
    y = np.array([10.0, 15.0, 20.0, 25.0])
    pipeline.fit(X, y)
    return pipeline


def _save_valid_qb_model(tmp_path):
    save_all_artifacts(
        tmp_path / "qb" / "v1", _real_pipeline(),
        {"model_version": MODEL_VERSION, "position": "QB", "target_scoring_version": TARGET_SCORING_VERSION},
        ["feature_a", "feature_b"], {"mae": 5.0},
        residual_intervals={"available": True, "p10_offset": -3.0, "p90_offset": 4.0},
    )


def test_load_valid_model_succeeds(tmp_path):
    _save_valid_qb_model(tmp_path)
    model = load_position_model("QB", artifact_root=tmp_path)
    assert model.position == "QB"
    assert model.feature_list == ["feature_a", "feature_b"]


def test_unsupported_position_rejected(tmp_path):
    with pytest.raises(NflModelArtifactError):
        load_position_model("LB", artifact_root=tmp_path)


def test_missing_metadata_raises(tmp_path):
    with pytest.raises(NflModelArtifactError):
        load_position_model("QB", artifact_root=tmp_path)


def test_wrong_model_version_rejected(tmp_path):
    save_all_artifacts(tmp_path / "qb" / "v1", _real_pipeline(), {"model_version": "nfl_v0_stale", "position": "QB", "target_scoring_version": TARGET_SCORING_VERSION}, ["a"], {"mae": 5.0})
    with pytest.raises(NflModelArtifactError, match="version"):
        load_position_model("QB", artifact_root=tmp_path)


def test_wrong_position_in_metadata_rejected(tmp_path):
    """Someone accidentally saved a WR-trained model into the qb/v1/
    directory -- must never load silently."""
    save_all_artifacts(tmp_path / "qb" / "v1", _real_pipeline(), {"model_version": MODEL_VERSION, "position": "WR", "target_scoring_version": TARGET_SCORING_VERSION}, ["a"], {"mae": 5.0})
    with pytest.raises(NflModelArtifactError, match="Position"):
        load_position_model("QB", artifact_root=tmp_path)


def test_wrong_target_scoring_version_rejected(tmp_path):
    save_all_artifacts(tmp_path / "qb" / "v1", _real_pipeline(), {"model_version": MODEL_VERSION, "position": "QB", "target_scoring_version": "dk_nfl_classic_v0_stale"}, ["a"], {"mae": 5.0})
    with pytest.raises(NflModelArtifactError, match="scoring"):
        load_position_model("QB", artifact_root=tmp_path)


def test_predict_one_imputes_missing_features(tmp_path):
    _save_valid_qb_model(tmp_path)
    model = load_position_model("QB", artifact_root=tmp_path)
    result = predict_one(model, {"feature_a": 2.5})  # feature_b missing entirely -- imputed, not treated as 0
    assert isinstance(result["projection"], float)


def test_predict_one_returns_floor_ceiling_when_intervals_available(tmp_path):
    _save_valid_qb_model(tmp_path)
    model = load_position_model("QB", artifact_root=tmp_path)
    result = predict_one(model, {"feature_a": 2.0, "feature_b": 3.0})
    assert result["floor"] == round(result["projection"] - 3.0, 2)
    assert result["ceiling"] == round(result["projection"] + 4.0, 2)


def test_predict_one_null_floor_ceiling_when_no_intervals(tmp_path):
    save_all_artifacts(tmp_path / "qb" / "v1", _real_pipeline(), {"model_version": MODEL_VERSION, "position": "QB", "target_scoring_version": TARGET_SCORING_VERSION}, ["feature_a", "feature_b"], {"mae": 5.0})
    model = load_position_model("QB", artifact_root=tmp_path)
    result = predict_one(model, {"feature_a": 2.0, "feature_b": 3.0})
    assert result["floor"] is None
    assert result["ceiling"] is None
