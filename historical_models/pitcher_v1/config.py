"""Milestone 32.2 -- constants shared across the pitcher_v1 package.
Single source of truth for the chronological split, artifact
locations, and the random seed -- nothing else in this package
hardcodes a date or a path.
"""

from pathlib import Path

from historical_models.pitcher_v1 import BIG_MONEY_PITCHER_MODEL_VERSION
from historical_mlb.paths import WAREHOUSE_VERSION

MODEL_VERSION = BIG_MONEY_PITCHER_MODEL_VERSION

DEFAULT_WAREHOUSE_PITCHER_PARQUET = Path("data/historical/mlb/processed/pitcher_game_features.parquet")
DEFAULT_ARTIFACT_DIR = Path("data/models/mlb/pitcher/v1")

# Milestone 32.2, Part "CHRONOLOGICAL SPLIT" -- verified against the
# real warehouse (367/367 dates collected in M32.1): these exact dates
# partition every starting-pitcher row with zero gap and zero overlap
# (7,386 train / 1,580 validation / 748 test = 9,714 total), so no
# adjustment was needed.
TRAIN_START, TRAIN_END = "2024-03-28", "2025-06-30"
VALIDATION_START, VALIDATION_END = "2025-07-01", "2025-08-31"
TEST_START, TEST_END = "2025-09-01", "2025-09-28"

DEFAULT_SEED = 42

TARGET_COLUMN = "actual_dk_points"

__all__ = [
    "MODEL_VERSION", "WAREHOUSE_VERSION", "DEFAULT_WAREHOUSE_PITCHER_PARQUET", "DEFAULT_ARTIFACT_DIR",
    "TRAIN_START", "TRAIN_END", "VALIDATION_START", "VALIDATION_END", "TEST_START", "TEST_END",
    "DEFAULT_SEED", "TARGET_COLUMN",
]
