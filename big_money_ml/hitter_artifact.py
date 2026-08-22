"""Milestone 32.3B -- frozen HITTER model artifact loading + fail-closed
compatibility validation. Mirrors artifact.py (pitcher) exactly, for
historical_models.hitter_v1 instead.

Unlike the pitcher artifact (a single fixed FEATURE_COLUMNS list), the
frozen hitter model may have been trained on EITHER the ALWAYS_PREGAME
or the AFTER_LINEUP feature set -- M32.3 froze AFTER_LINEUP. This loader
validates the artifact's declared feature_availability_class matches
its own feature_list (via features.feature_columns_for), not a single
hardcoded list.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from historical_models.hitter_v1.config import DEFAULT_ARTIFACT_DIR, MODEL_VERSION
from historical_models.hitter_v1.features import feature_columns_for
from historical_models.hitter_v1.persistence import FEATURE_LIST_FILENAME, METADATA_FILENAME, load_json, load_model

EXPECTED_MODEL_VERSION = MODEL_VERSION  # "1.0.0" -- Hitter Model V1


class HitterModelArtifactError(Exception):
    """Raised when the frozen hitter artifact is missing, unreadable, or
    incompatible with this package's expected version/feature schema.
    Callers must treat this as STOP LIVE INFERENCE, never a reason to
    substitute a default."""


@dataclass
class FrozenHitterModelArtifact:
    pipeline: Any
    metadata: dict
    feature_list: List[str]
    feature_availability_class: str
    artifact_dir: Path
    model_version: str


def load_and_validate_frozen_hitter_model(artifact_dir: Optional[Path] = None) -> FrozenHitterModelArtifact:
    artifact_dir = Path(artifact_dir or DEFAULT_ARTIFACT_DIR)

    metadata = load_json(artifact_dir, METADATA_FILENAME)
    if metadata is None:
        raise HitterModelArtifactError(f"No model metadata found at {artifact_dir / METADATA_FILENAME} -- run historical_models.hitter_v1.train first.")

    feature_list = load_json(artifact_dir, FEATURE_LIST_FILENAME)
    if feature_list is None:
        raise HitterModelArtifactError(f"No feature list found at {artifact_dir / FEATURE_LIST_FILENAME}.")

    model_version = metadata.get("model_version")
    if model_version != EXPECTED_MODEL_VERSION:
        raise HitterModelArtifactError(
            f"Frozen hitter artifact model_version={model_version!r} does not match the expected "
            f"Hitter Model V1 version {EXPECTED_MODEL_VERSION!r} -- refusing to run an unverified model."
        )

    feature_availability_class = metadata.get("feature_availability_class")
    if feature_availability_class not in ("ALWAYS_PREGAME", "AFTER_LINEUP"):
        raise HitterModelArtifactError(f"Frozen hitter artifact has an unrecognized feature_availability_class: {feature_availability_class!r}.")

    expected_features = feature_columns_for(feature_availability_class)
    if list(feature_list) != list(expected_features):
        raise HitterModelArtifactError(
            "Frozen hitter artifact's feature_list.json does not exactly match the current "
            f"historical_models.hitter_v1.features schema for {feature_availability_class!r} -- refusing to run "
            "an incompatible model against a feature schema it wasn't trained on."
        )

    try:
        pipeline = load_model(artifact_dir)
    except Exception as exc:  # noqa: BLE001 -- any load failure is fail-closed, not a crash
        raise HitterModelArtifactError(f"Failed to load model.joblib from {artifact_dir}: {exc}") from exc

    return FrozenHitterModelArtifact(
        pipeline=pipeline, metadata=metadata, feature_list=list(feature_list),
        feature_availability_class=feature_availability_class, artifact_dir=artifact_dir, model_version=model_version,
    )
