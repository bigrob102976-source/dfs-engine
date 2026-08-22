"""Milestone 32.3 -- constants shared across the hitter_v1 package.
Single source of truth for the chronological split, artifact
locations, and the random seed -- nothing else in this package
hardcodes a date or a path. Mirrors historical_models.pitcher_v1.config
exactly (same split dates -- verified below to also gap-free-partition
the hitter warehouse).
"""

from pathlib import Path

from historical_models.hitter_v1 import BIG_MONEY_HITTER_MODEL_VERSION
from historical_mlb.paths import WAREHOUSE_VERSION

MODEL_VERSION = BIG_MONEY_HITTER_MODEL_VERSION

DEFAULT_WAREHOUSE_HITTER_PARQUET = Path("data/historical/mlb/processed/hitter_game_features.parquet")
DEFAULT_ARTIFACT_DIR = Path("data/models/mlb/hitter/v1")

# Milestone 32.3 -- verified against the real warehouse: these exact
# dates partition every hitter row with zero gap and zero overlap
# (77,018 train / 16,482 validation / 8,094 test = 101,594 total), the
# same as Pitcher Model V1's own split -- no adjustment was needed.
TRAIN_START, TRAIN_END = "2024-03-28", "2025-06-30"
VALIDATION_START, VALIDATION_END = "2025-07-01", "2025-08-31"
TEST_START, TEST_END = "2025-09-01", "2025-09-28"

DEFAULT_SEED = 42

TARGET_COLUMN = "actual_dk_points"

# Milestone 32.3's two feature-availability experiments -- see features.py.
ALWAYS_PREGAME = "ALWAYS_PREGAME"
AFTER_LINEUP = "AFTER_LINEUP"

__all__ = [
    "MODEL_VERSION", "WAREHOUSE_VERSION", "DEFAULT_WAREHOUSE_HITTER_PARQUET", "DEFAULT_ARTIFACT_DIR",
    "TRAIN_START", "TRAIN_END", "VALIDATION_START", "VALIDATION_END", "TEST_START", "TEST_END",
    "DEFAULT_SEED", "TARGET_COLUMN", "ALWAYS_PREGAME", "AFTER_LINEUP",
]
