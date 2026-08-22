"""Milestone 32.3 -- model metadata record. Reuses the generic (non-
pitcher-specific) _git_commit/_library_versions helpers directly from
historical_models.pitcher_v1.metadata via import -- both are pure,
model-agnostic utilities (git commit lookup, installed library
versions), so importing them here is a read-only dependency, never a
modification of the Pitcher Model V1 package, and avoids a duplicate
generic utility per CLAUDE.md's "prefer simple code, avoid duplication."
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from historical_models.pitcher_v1.metadata import _git_commit, _library_versions

from historical_models.hitter_v1.config import (
    DEFAULT_SEED, MODEL_VERSION, TARGET_COLUMN, TEST_END, TEST_START,
    TRAIN_END, TRAIN_START, VALIDATION_END, VALIDATION_START, WAREHOUSE_VERSION,
)


@dataclass
class ModelMetadata:
    model_version: str = MODEL_VERSION
    warehouse_version: str = WAREHOUSE_VERSION
    target_column: str = TARGET_COLUMN
    train_date_range: tuple = (TRAIN_START, TRAIN_END)
    validation_date_range: tuple = (VALIDATION_START, VALIDATION_END)
    test_date_range: tuple = (TEST_START, TEST_END)
    feature_availability_class: str = ""  # "ALWAYS_PREGAME" | "AFTER_LINEUP"
    feature_list: List[str] = field(default_factory=list)
    model_type: str = ""
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    seed: int = DEFAULT_SEED
    library_versions: Dict[str, str] = field(default_factory=_library_versions)
    git_commit: Optional[str] = field(default_factory=_git_commit)
    training_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    salary_used_as_feature: bool = False
    vegas_used_as_feature: bool = False
    player_id_used_as_feature: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
