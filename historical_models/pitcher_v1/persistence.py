"""Milestone 32.2 -- save/load the trained model + every evaluation
artifact. All under a gitignored directory (data/models/mlb/pitcher/v1/,
mirroring the same "generated data is never committed" discipline
M32.0/M32.1 already established for data/historical/)."""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import joblib

from historical_models.pitcher_v1.config import DEFAULT_ARTIFACT_DIR

MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"
FEATURE_LIST_FILENAME = "feature_list.json"
VALIDATION_METRICS_FILENAME = "validation_metrics.json"
TEST_METRICS_FILENAME = "test_metrics.json"
FEATURE_IMPORTANCE_FILENAME = "feature_importance.json"
CALIBRATION_FILENAME = "calibration.json"
OUTLIERS_FILENAME = "outliers.json"
EXPERIMENTS_FILENAME = "experiments.jsonl"


def save_json(output_dir: Path, filename: str, payload: Any) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def load_json(output_dir: Path, filename: str) -> Optional[Any]:
    path = output_dir / filename
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def save_model(output_dir: Path, pipeline) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MODEL_FILENAME
    joblib.dump(pipeline, path)
    return path


def load_model(output_dir: Path):
    return joblib.load(output_dir / MODEL_FILENAME)


def append_experiment_record(output_dir: Path, record: Dict) -> None:
    """Milestone 32.2's "Experiment tracking" -- append-only, never
    overwrites a previous experiment's row."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / EXPERIMENTS_FILENAME
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def save_all_artifacts(
    output_dir: Path, pipeline, metadata: dict, feature_list: list,
    validation_metrics: dict, test_metrics: Optional[dict] = None,
    feature_importance: Optional[list] = None, calibration: Optional[list] = None, outliers: Optional[dict] = None,
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
    if outliers is not None:
        paths["outliers"] = save_json(output_dir, OUTLIERS_FILENAME, outliers)
    return paths
