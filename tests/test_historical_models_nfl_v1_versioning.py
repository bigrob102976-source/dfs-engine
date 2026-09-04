"""NFL M11 -- targeted tests for per-position artifact version
resolution (Phase 13: DST moves to v2, offense stays v1, prior versions
never overwritten)."""

from sklearn.linear_model import Ridge

from historical_models.nfl_v1.config import CURRENT_ARTIFACT_VERSION_BY_POSITION, MODEL_VERSION, TARGET_SCORING_VERSION
from historical_models.nfl_v1.inference import load_position_model
from historical_models.nfl_v1.persistence import save_all_artifacts


def _save(output_dir):
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    import numpy as np
    pipeline = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", Ridge())])
    pipeline.fit(np.array([[1.0], [2.0], [3.0]]), np.array([1.0, 2.0, 3.0]))
    save_all_artifacts(output_dir, pipeline, {"model_version": MODEL_VERSION, "position": "DST", "target_scoring_version": TARGET_SCORING_VERSION}, ["a"], {"mae": 1.0})


def test_dst_defaults_to_v2(tmp_path):
    assert CURRENT_ARTIFACT_VERSION_BY_POSITION["DST"] == "v2"
    _save(tmp_path / "dst" / "v2")
    model = load_position_model("DST", artifact_root=tmp_path)
    assert model.position == "DST"


def test_offense_positions_default_to_v1():
    for pos in ("QB", "RB", "WR", "TE"):
        assert CURRENT_ARTIFACT_VERSION_BY_POSITION[pos] == "v1"


def test_explicit_version_overrides_default(tmp_path):
    _save(tmp_path / "dst" / "v3")
    model = load_position_model("DST", artifact_root=tmp_path, version="v3")
    assert model.position == "DST"


def test_prior_version_untouched_when_new_version_saved(tmp_path):
    """A real safety property: saving v2 must never touch/require v1 to
    exist or be removed."""
    _save(tmp_path / "dst" / "v1")
    _save(tmp_path / "dst" / "v2")
    assert (tmp_path / "dst" / "v1" / "model.joblib").exists()
    assert (tmp_path / "dst" / "v2" / "model.joblib").exists()
