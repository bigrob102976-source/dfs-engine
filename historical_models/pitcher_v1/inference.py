"""Milestone 32.2 -- clean inference interface.

    predict_pitcher(features) -> PitcherModelPrediction

Loads the frozen artifact saved by train.py and scores one pitcher's
pregame feature dict. This module is evaluation-tooling only: nothing
in the live optimizer, agents, or dashboard imports it yet, per this
milestone's explicit "do NOT wire into production optimizer yet"
instruction. See historical_models/pitcher_v1/__init__.py.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from historical_models.pitcher_v1.config import DEFAULT_ARTIFACT_DIR, MODEL_VERSION
from historical_models.pitcher_v1.features import FEATURE_COLUMNS, assert_no_leakage
from historical_models.pitcher_v1.persistence import METADATA_FILENAME, load_json, load_model

# Families the spec calls out by name for the data-quality composite
# ("feature completeness, historical sample coverage, Statcast
# availability, rolling history availability") -- statcast/rolling
# coverage checked explicitly in addition to overall coverage below.
_STATCAST_PREFIX = "statcast_"
_ROLLING_PREFIX = "rolling_"


@dataclass
class PitcherModelPrediction:
    player_id: str
    projection: float
    model_version: str
    feature_coverage: float
    missing_features: List[str]
    # NOT a calibrated probability of correctness -- a composite of how
    # complete this pitcher's inputs are (overall / Statcast / rolling
    # history coverage). Never hardcoded; never presented as "confidence."
    data_quality_score: float


def _family_coverage(row: Dict[str, Any], prefix: str) -> Optional[float]:
    cols = [c for c in FEATURE_COLUMNS if c.startswith(prefix)]
    if not cols:
        return None
    available = sum(1 for c in cols if row.get(c) is not None)
    return available / len(cols)


def predict_pitcher(features: Dict[str, Any], artifact_dir: Optional[Path] = None) -> PitcherModelPrediction:
    assert_no_leakage(list(features.keys()))
    artifact_dir = Path(artifact_dir or DEFAULT_ARTIFACT_DIR)
    pipeline = load_model(artifact_dir)
    metadata = load_json(artifact_dir, METADATA_FILENAME) or {}

    row = {col: features.get(col) for col in FEATURE_COLUMNS}
    missing_features = [col for col, value in row.items() if value is None]
    feature_coverage = round(1.0 - len(missing_features) / len(FEATURE_COLUMNS), 4) if FEATURE_COLUMNS else 0.0

    X = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    projection = float(pipeline.predict(X)[0])

    component_scores = [feature_coverage]
    for prefix in (_STATCAST_PREFIX, _ROLLING_PREFIX):
        cov = _family_coverage(row, prefix)
        if cov is not None:
            component_scores.append(cov)
    data_quality_score = round(sum(component_scores) / len(component_scores), 4)

    return PitcherModelPrediction(
        player_id=str(features.get("player_id", "")),
        projection=round(projection, 3),
        model_version=metadata.get("model_version", MODEL_VERSION),
        feature_coverage=feature_coverage,
        missing_features=missing_features,
        data_quality_score=data_quality_score,
    )
