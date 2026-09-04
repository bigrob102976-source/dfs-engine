"""NFL M10 -- constants shared across the nfl_v1 model package. Mirrors
historical_models/pitcher_v1/config.py's exact discipline (single
source of truth for splits, artifact locations, seed).

One model per position, parametrized rather than five duplicated
packages -- artifact dir is data/models/nfl/{position}/v1/."""

from pathlib import Path

from historical_models.nfl_v1 import BIG_MONEY_NFL_MODEL_VERSION

MODEL_VERSION = BIG_MONEY_NFL_MODEL_VERSION

DATASET_SCHEMA_VERSION = "nfl_projection_training_v1"
TARGET_SCORING_VERSION = "dk_nfl_classic_v1"

DEFAULT_ARTIFACT_ROOT = Path("data/models/nfl")

OFFENSE_POSITIONS = ("QB", "RB", "WR", "TE")
DST_POSITION = "DST"
ALL_POSITIONS = OFFENSE_POSITIONS + (DST_POSITION,)

SPLIT_TRAIN = "train"
SPLIT_VALIDATION = "validation"
SPLIT_TEST = "test"

DEFAULT_SEED = 42

TARGET_COLUMN = "target_dk_points"

# Rolling/season-to-date feature keys that are pure identifiers or
# leakage-adjacent metadata, never fed to a model as a numeric feature.
NON_FEATURE_ROLLING_KEYS = ("weeks_of_history",)

__all__ = [
    "MODEL_VERSION", "DATASET_SCHEMA_VERSION", "TARGET_SCORING_VERSION", "DEFAULT_ARTIFACT_ROOT",
    "OFFENSE_POSITIONS", "DST_POSITION", "ALL_POSITIONS", "SPLIT_TRAIN", "SPLIT_VALIDATION", "SPLIT_TEST",
    "DEFAULT_SEED", "TARGET_COLUMN", "NON_FEATURE_ROLLING_KEYS",
]
