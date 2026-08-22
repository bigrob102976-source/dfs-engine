"""Milestone 32.3 -- save/load the trained model + every evaluation
artifact. Reuses the generic (model-agnostic) save_json/load_json/
save_model/load_model/append_experiment_record helpers directly from
historical_models.pitcher_v1.persistence via import -- none of them
contain pitcher-specific logic (they operate on arbitrary paths/dicts),
so importing is a read-only dependency, never a modification of the
Pitcher Model V1 package, and avoids a duplicate generic utility.

All artifacts live under a gitignored directory
(data/models/mlb/hitter/v1/), mirroring the same "generated data is
never committed" discipline pitcher_v1/results already established.
"""

from pathlib import Path
from typing import Dict, Optional

from historical_models.pitcher_v1.persistence import append_experiment_record, load_json, load_model, save_json, save_model

from historical_models.hitter_v1.config import DEFAULT_ARTIFACT_DIR

MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"
FEATURE_LIST_FILENAME = "feature_list.json"
VALIDATION_METRICS_FILENAME = "validation_metrics.json"
TEST_METRICS_FILENAME = "test_metrics.json"
FEATURE_IMPORTANCE_FILENAME = "feature_importance.json"
CALIBRATION_FILENAME = "calibration.json"
CEILING_ANALYSIS_FILENAME = "ceiling_analysis.json"
OUTLIERS_FILENAME = "outliers.json"
EXPERIMENTS_FILENAME = "experiments.jsonl"

__all__ = [
    "save_json", "load_json", "save_model", "load_model", "append_experiment_record",
    "MODEL_FILENAME", "METADATA_FILENAME", "FEATURE_LIST_FILENAME", "VALIDATION_METRICS_FILENAME",
    "TEST_METRICS_FILENAME", "FEATURE_IMPORTANCE_FILENAME", "CALIBRATION_FILENAME",
    "CEILING_ANALYSIS_FILENAME", "OUTLIERS_FILENAME", "EXPERIMENTS_FILENAME",
    "save_all_artifacts",
]


def save_all_artifacts(
    output_dir: Path, pipeline, metadata: dict, feature_list: list,
    validation_metrics: dict, test_metrics: Optional[dict] = None,
    feature_importance: Optional[list] = None, calibration: Optional[list] = None,
    ceiling_analysis: Optional[dict] = None, outliers: Optional[dict] = None,
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
    if calibration is not None:
        paths["calibration"] = save_json(output_dir, CALIBRATION_FILENAME, calibration)
    if ceiling_analysis is not None:
        paths["ceiling_analysis"] = save_json(output_dir, CEILING_ANALYSIS_FILENAME, ceiling_analysis)
    if outliers is not None:
        paths["outliers"] = save_json(output_dir, OUTLIERS_FILENAME, outliers)
    return paths
