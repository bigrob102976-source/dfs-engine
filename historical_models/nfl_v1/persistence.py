"""NFL M10 -- save/load trained NFL models + every evaluation artifact.
Reuses the generic (sport-agnostic) save_json/load_json/save_model/
load_model helpers directly from historical_models.pitcher_v1.persistence
via import -- none of them contain MLB-specific logic (they operate on
arbitrary paths/dicts/joblib pipelines), so importing is a read-only
dependency, never a modification of the MLB package, mirroring hitter_
v1/persistence.py's own exact precedent for reusing pitcher_v1's
generic utilities rather than duplicating them.

All artifacts live under data/models/nfl/{position}/v1/ -- gitignored
(/data/models/ already covers it, established M32.2/M32.3 for MLB),
never committed, matching this project's "generated model artifacts are
never committed" precedent exactly."""

from pathlib import Path
from typing import Dict, Optional

from historical_models.pitcher_v1.persistence import load_json, load_model, save_json, save_model

MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"
FEATURE_LIST_FILENAME = "feature_list.json"
VALIDATION_METRICS_FILENAME = "validation_metrics.json"
TEST_METRICS_FILENAME = "test_metrics.json"
FEATURE_IMPORTANCE_FILENAME = "feature_importance.json"
OUTLIERS_FILENAME = "outliers.json"
RESIDUAL_INTERVALS_FILENAME = "residual_intervals.json"

__all__ = [
    "save_json", "load_json", "save_model", "load_model",
    "MODEL_FILENAME", "METADATA_FILENAME", "FEATURE_LIST_FILENAME", "VALIDATION_METRICS_FILENAME",
    "TEST_METRICS_FILENAME", "FEATURE_IMPORTANCE_FILENAME", "OUTLIERS_FILENAME", "RESIDUAL_INTERVALS_FILENAME",
    "save_all_artifacts", "load_all_artifacts",
]


def save_all_artifacts(
    output_dir: Path, pipeline, metadata: dict, feature_list: list,
    validation_metrics: dict, test_metrics: Optional[dict] = None,
    feature_importance: Optional[list] = None, outliers: Optional[dict] = None,
    residual_intervals: Optional[dict] = None,
) -> Dict[str, Path]:
    output_dir = Path(output_dir)
    paths = {
        "model": save_model(output_dir, pipeline),
        "metadata": save_json(output_dir, METADATA_FILENAME, metadata),
        "feature_list": save_json(output_dir, FEATURE_LIST_FILENAME, feature_list),
        "validation_metrics": save_json(output_dir, VALIDATION_METRICS_FILENAME, validation_metrics),
    }
    if test_metrics is not None:
        paths["test_metrics"] = save_json(output_dir, TEST_METRICS_FILENAME, test_metrics)
    if feature_importance is not None:
        paths["feature_importance"] = save_json(output_dir, FEATURE_IMPORTANCE_FILENAME, feature_importance)
    if outliers is not None:
        paths["outliers"] = save_json(output_dir, OUTLIERS_FILENAME, outliers)
    if residual_intervals is not None:
        paths["residual_intervals"] = save_json(output_dir, RESIDUAL_INTERVALS_FILENAME, residual_intervals)
    return paths


def load_all_artifacts(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    return {
        "model": load_model(output_dir),
        "metadata": load_json(output_dir, METADATA_FILENAME),
        "feature_list": load_json(output_dir, FEATURE_LIST_FILENAME),
        "residual_intervals": load_json(output_dir, RESIDUAL_INTERVALS_FILENAME),
    }
