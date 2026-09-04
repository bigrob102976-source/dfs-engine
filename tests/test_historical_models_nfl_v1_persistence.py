"""NFL M10 -- targeted tests for historical_models/nfl_v1/persistence.py."""

from sklearn.linear_model import Ridge

from historical_models.nfl_v1.persistence import load_all_artifacts, save_all_artifacts


def test_save_and_load_round_trips(tmp_path):
    model = Ridge()
    metadata = {"model_version": "nfl_v1", "position": "QB"}
    feature_list = ["carries_mean_last1", "targets_mean_last1"]
    validation_metrics = {"mae": 5.0}

    save_all_artifacts(tmp_path, model, metadata, feature_list, validation_metrics, test_metrics={"mae": 5.5}, residual_intervals={"available": True, "p10_offset": -3.0, "p90_offset": 3.0})
    loaded = load_all_artifacts(tmp_path)

    assert loaded["metadata"]["position"] == "QB"
    assert loaded["feature_list"] == feature_list
    assert loaded["residual_intervals"]["p10_offset"] == -3.0
    assert isinstance(loaded["model"], Ridge)


def test_optional_artifacts_omitted_when_not_provided(tmp_path):
    model = Ridge()
    save_all_artifacts(tmp_path, model, {"position": "RB"}, [], {"mae": 1.0})
    assert not (tmp_path / "test_metrics.json").exists()
    assert not (tmp_path / "residual_intervals.json").exists()
