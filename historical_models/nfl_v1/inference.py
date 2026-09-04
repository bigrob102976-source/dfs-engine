"""NFL M10 -- offline inference: loads a position's persisted nfl_v1
artifact and predicts DK points for a real feature row.

STRICT validation (Phase 14): every load checks model_version, position,
dataset schema version, and target scoring version before ever calling
.predict() -- a version/position/schema mismatch raises, never silently
loads an incompatible artifact. Floor/ceiling use the persisted
residual_intervals (Phase 11's empirical, validation-derived offsets) --
null when unavailable, never an arbitrary multiplier.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from historical_models.nfl_v1.config import DEFAULT_ARTIFACT_ROOT, DST_POSITION, MODEL_VERSION, OFFENSE_POSITIONS, TARGET_SCORING_VERSION
from historical_models.nfl_v1.persistence import load_all_artifacts


class NflModelArtifactError(RuntimeError):
    """A persisted artifact failed strict validation -- never loaded and
    used anyway."""


@dataclass
class LoadedNflModel:
    position: str
    pipeline: object
    feature_list: List[str]
    residual_intervals: Optional[dict]
    metadata: dict


def load_position_model(position: str, artifact_root: Path = DEFAULT_ARTIFACT_ROOT) -> LoadedNflModel:
    if position not in OFFENSE_POSITIONS and position != DST_POSITION:
        raise NflModelArtifactError(f"{position!r} is not a supported NFL model position.")

    output_dir = Path(artifact_root) / position.lower() / "v1"
    try:
        artifacts = load_all_artifacts(output_dir)
    except FileNotFoundError as exc:
        raise NflModelArtifactError(f"No model artifact found for position {position!r} at {output_dir}: {exc}") from exc
    metadata = artifacts["metadata"]
    if metadata is None:
        raise NflModelArtifactError(f"No metadata.json found for position {position!r} at {output_dir}.")

    if metadata.get("model_version") != MODEL_VERSION:
        raise NflModelArtifactError(f"Model version mismatch: artifact={metadata.get('model_version')!r}, expected={MODEL_VERSION!r}.")
    if metadata.get("position") != position:
        raise NflModelArtifactError(f"Position mismatch: artifact={metadata.get('position')!r}, requested={position!r}.")
    if metadata.get("target_scoring_version") != TARGET_SCORING_VERSION:
        raise NflModelArtifactError(f"Target scoring version mismatch: artifact={metadata.get('target_scoring_version')!r}, expected={TARGET_SCORING_VERSION!r}.")
    if artifacts["feature_list"] is None:
        raise NflModelArtifactError(f"No feature_list.json found for position {position!r}.")

    return LoadedNflModel(
        position=position, pipeline=artifacts["model"], feature_list=artifacts["feature_list"],
        residual_intervals=artifacts["residual_intervals"], metadata=metadata,
    )


def predict_one(model: LoadedNflModel, feature_row: Dict[str, Optional[float]]) -> dict:
    """`feature_row` must carry every key in model.feature_list (missing
    keys become NaN, imputed by the persisted pipeline's own train-only-
    fit imputer -- never silently treated as 0). Returns {"projection",
    "floor", "ceiling"} -- floor/ceiling are None when no real residual
    interval was persisted for this position (Phase 11: never fabricated)."""
    row = {k: feature_row.get(k) for k in model.feature_list}
    X = pd.DataFrame([row], columns=model.feature_list)
    raw_projection = float(model.pipeline.predict(X)[0])
    # See historical_models/nfl_v1/train.py::_clamp_predictions' docstring:
    # a real, observed Ridge extrapolation blowup (-104.94 for an actual
    # 0.0 RB game) during M10 training -- never let a live projection be
    # worse than the worst real game this position has ever recorded.
    prediction_floor = model.metadata.get("prediction_floor")
    projection = max(raw_projection, prediction_floor) if prediction_floor is not None else raw_projection

    floor = ceiling = None
    intervals = model.residual_intervals
    if intervals and intervals.get("available"):
        floor = round(projection + intervals["p10_offset"], 2)
        ceiling = round(projection + intervals["p90_offset"], 2)

    return {"projection": round(projection, 2), "floor": floor, "ceiling": ceiling}
