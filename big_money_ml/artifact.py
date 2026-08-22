"""Milestone 32.2B -- frozen model artifact loading + fail-closed
compatibility validation.

Loads the EXACT frozen M32.2 winning artifact (model.joblib +
metadata.json + feature_list.json) saved by
historical_models.pitcher_v1.train. Never retrains, never re-fits,
never adjusts hyperparameters. If the loaded artifact's model_version
or feature schema doesn't match what this package expects, inference
is refused (fail closed) rather than silently running an incompatible
model.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from historical_models.pitcher_v1.config import DEFAULT_ARTIFACT_DIR, MODEL_VERSION
from historical_models.pitcher_v1.features import FEATURE_COLUMNS
from historical_models.pitcher_v1.persistence import (
    FEATURE_LIST_FILENAME,
    METADATA_FILENAME,
    load_json,
    load_model,
)

EXPECTED_MODEL_VERSION = MODEL_VERSION  # "1.0.0" -- Pitcher Model V1


class ModelArtifactError(Exception):
    """Raised when the frozen artifact is missing, unreadable, or
    incompatible with this package's expected version/feature schema.
    Callers must treat this as STOP LIVE INFERENCE, never a reason to
    substitute a default."""


@dataclass
class FrozenModelArtifact:
    pipeline: Any
    metadata: dict
    feature_list: List[str]
    artifact_dir: Path
    model_version: str


def load_and_validate_frozen_pitcher_model(artifact_dir: Optional[Path] = None) -> FrozenModelArtifact:
    artifact_dir = Path(artifact_dir or DEFAULT_ARTIFACT_DIR)

    metadata = load_json(artifact_dir, METADATA_FILENAME)
    if metadata is None:
        raise ModelArtifactError(f"No model metadata found at {artifact_dir / METADATA_FILENAME} -- run historical_models.pitcher_v1.train first.")

    feature_list = load_json(artifact_dir, FEATURE_LIST_FILENAME)
    if feature_list is None:
        raise ModelArtifactError(f"No feature list found at {artifact_dir / FEATURE_LIST_FILENAME}.")

    model_version = metadata.get("model_version")
    if model_version != EXPECTED_MODEL_VERSION:
        raise ModelArtifactError(
            f"Frozen artifact model_version={model_version!r} does not match the expected "
            f"Pitcher Model V1 version {EXPECTED_MODEL_VERSION!r} -- refusing to run an unverified model."
        )

    if list(feature_list) != list(FEATURE_COLUMNS):
        raise ModelArtifactError(
            "Frozen artifact's feature_list.json does not exactly match the current "
            "historical_models.pitcher_v1.features.FEATURE_COLUMNS schema -- refusing to run an "
            "incompatible model against a feature schema it wasn't trained on."
        )

    try:
        pipeline = load_model(artifact_dir)
    except Exception as exc:  # noqa: BLE001 -- any load failure is fail-closed, not a crash
        raise ModelArtifactError(f"Failed to load model.joblib from {artifact_dir}: {exc}") from exc

    return FrozenModelArtifact(
        pipeline=pipeline, metadata=metadata, feature_list=list(feature_list),
        artifact_dir=artifact_dir, model_version=model_version,
    )
