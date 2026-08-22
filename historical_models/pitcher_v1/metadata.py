"""Milestone 32.2 -- model metadata record. Every field this milestone's
"Persist" instruction lists, in one place."""

import platform
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from historical_models.pitcher_v1.config import (
    DEFAULT_SEED, MODEL_VERSION, TARGET_COLUMN, TEST_END, TEST_START,
    TRAIN_END, TRAIN_START, VALIDATION_END, VALIDATION_START, WAREHOUSE_VERSION,
)


def _git_commit() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001 -- best-effort only, never blocks training
        return None


def _library_versions() -> Dict[str, str]:
    import numpy
    import pandas
    import sklearn

    return {"python": platform.python_version(), "sklearn": sklearn.__version__, "pandas": pandas.__version__, "numpy": numpy.__version__}


@dataclass
class ModelMetadata:
    model_version: str = MODEL_VERSION
    warehouse_version: str = WAREHOUSE_VERSION
    target_column: str = TARGET_COLUMN
    train_date_range: tuple = (TRAIN_START, TRAIN_END)
    validation_date_range: tuple = (VALIDATION_START, VALIDATION_END)
    test_date_range: tuple = (TEST_START, TEST_END)
    feature_list: List[str] = field(default_factory=list)
    model_type: str = ""
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    seed: int = DEFAULT_SEED
    library_versions: Dict[str, str] = field(default_factory=_library_versions)
    git_commit: Optional[str] = field(default_factory=_git_commit)
    training_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    salary_used_as_feature: bool = False
    vegas_used_as_feature: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
