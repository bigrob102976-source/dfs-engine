"""Milestone 32.3 -- clean inference interface.

    predict_hitter(features) -> HitterModelPrediction

Loads the frozen artifact saved by train.py and scores one hitter's
pregame feature dict. Evaluation-tooling only: nothing in the live
optimizer, agents, or dashboard imports this yet -- shadow-live
inference is an explicitly separate, FUTURE milestone (M32.3B), not
performed here. See historical_models/hitter_v1/__init__.py.

Unlike pitcher_v1 (a single fixed FEATURE_COLUMNS list), the frozen
hitter model may have been trained on EITHER the ALWAYS_PREGAME or the
AFTER_LINEUP feature set -- which one is only known after training, so
this module reads feature_list.json from the artifact directory itself
rather than assuming a fixed column list.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from historical_models.hitter_v1.config import DEFAULT_ARTIFACT_DIR, MODEL_VERSION
from historical_models.hitter_v1.features import assert_no_leakage
from historical_models.hitter_v1.persistence import FEATURE_LIST_FILENAME, METADATA_FILENAME, load_json, load_model

_STATCAST_PREFIX = "statcast_"
_ROLLING_PREFIX = "rolling_"

# Retained strictly for joining/evaluation/reporting -- never fed to the
# model (feature_list never contains these, see features.py's
# _AFTER_LINEUP_IDENTITY_RISK / _BOOKKEEPING_ONLY).
_ALLOWED_IDENTITY_KEYS_IN_INPUT = {"player_id", "player_name", "opposing_starting_pitcher_id"}


@dataclass
class HitterModelPrediction:
    player_id: str
    projection: float
    model_version: str
    feature_availability_class: str
    feature_coverage: float
    missing_features: List[str]
    # NOT a calibrated probability of correctness -- a composite of how
    # complete this hitter's inputs are (overall / Statcast / rolling
    # history coverage). Never hardcoded; never presented as "confidence."
    data_quality_score: float


def _family_coverage(row: Dict[str, Any], feature_list: List[str], prefix: str) -> Optional[float]:
    cols = [c for c in feature_list if c.startswith(prefix)]
    if not cols:
        return None
    available = sum(1 for c in cols if row.get(c) is not None)
    return available / len(cols)


def predict_hitter(features: Dict[str, Any], artifact_dir: Optional[Path] = None) -> HitterModelPrediction:
    artifact_dir = Path(artifact_dir or DEFAULT_ARTIFACT_DIR)
    feature_list = load_json(artifact_dir, FEATURE_LIST_FILENAME)
    if feature_list is None:
        raise FileNotFoundError(f"No feature_list.json found under {artifact_dir} -- run historical_models.hitter_v1.train first.")
    metadata = load_json(artifact_dir, METADATA_FILENAME) or {}

    # Identity fields are explicitly allowed in the CALLER's input dict
    # (retained for joining/evaluation/reporting -- see the milestone's
    # "PLAYER IDENTITY" section) -- they're simply never in feature_list,
    # so they're excluded from `row`/`X` below regardless. Only check the
    # non-identity keys for genuinely dangerous (outcome/salary/Vegas)
    # columns, and separately verify the ARTIFACT's own declared
    # feature_list is clean (defense against a corrupted/tampered artifact).
    non_identity_keys = [k for k in features.keys() if k not in _ALLOWED_IDENTITY_KEYS_IN_INPUT]
    assert_no_leakage(non_identity_keys)
    assert_no_leakage(feature_list)
    pipeline = load_model(artifact_dir)

    row = {col: features.get(col) for col in feature_list}
    missing_features = [col for col, value in row.items() if value is None]
    feature_coverage = round(1.0 - len(missing_features) / len(feature_list), 4) if feature_list else 0.0

    X = pd.DataFrame([row], columns=feature_list)
    projection = float(pipeline.predict(X)[0])

    component_scores = [feature_coverage]
    for prefix in (_STATCAST_PREFIX, _ROLLING_PREFIX):
        cov = _family_coverage(row, feature_list, prefix)
        if cov is not None:
            component_scores.append(cov)
    data_quality_score = round(sum(component_scores) / len(component_scores), 4)

    return HitterModelPrediction(
        player_id=str(features.get("player_id", "")),
        projection=round(projection, 3),
        model_version=metadata.get("model_version", MODEL_VERSION),
        feature_availability_class=metadata.get("feature_availability_class", ""),
        feature_coverage=feature_coverage,
        missing_features=missing_features,
        data_quality_score=data_quality_score,
    )
