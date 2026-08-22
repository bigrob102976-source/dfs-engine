"""Milestone 32.3 -- load the warehouse, apply the chronological split.
No model logic here -- this module is pure data loading/splitting, kept
separate so it's testable without touching sklearn at all. Mirrors
historical_models.pitcher_v1.dataset exactly.

Hitter-only filtering / pitcher exclusion (per the milestone's explicit
test requirement): hitter_game_features.parquet is built exclusively
from box-score BATTING stat blocks by historical_mlb.hitter_features.py
(Milestone 32.1) -- a pitcher who never batted never gets a row here at
all, structurally, not via a runtime filter. A genuine two-way player
(e.g. a pitcher who also DH'd/batted a game) correctly gets a hitter row
for that game -- that's a real plate appearance, not a leak. See
dataset_test's cross-file check against the pitcher warehouse for the
one thing that IS worth verifying: that this file was never
accidentally built from pitching stat blocks.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from historical_models.hitter_v1.config import (
    DEFAULT_WAREHOUSE_HITTER_PARQUET, TARGET_COLUMN, TEST_END, TEST_START,
    TRAIN_END, TRAIN_START, VALIDATION_END, VALIDATION_START,
)


@dataclass
class DatasetSummary:
    total_rows: int
    train_rows: int
    validation_rows: int
    test_rows: int
    train_dates: tuple
    validation_dates: tuple
    test_dates: tuple
    unique_hitters: int
    unique_games: int
    unique_teams: int


def load_hitter_dataset(parquet_path: Optional[Path] = None) -> pd.DataFrame:
    """Loads hitter_game_features.parquet -- already hitter-only by
    construction (see module docstring). Sorted chronologically for
    reproducibility."""
    path = parquet_path or DEFAULT_WAREHOUSE_HITTER_PARQUET
    df = pd.read_parquet(path)
    df = df.sort_values(["game_date", "game_pk", "player_id"]).reset_index(drop=True)
    return df


def chronological_split(df: pd.DataFrame) -> tuple:
    """TRAIN / VALIDATION / TEST by game_date, per config.py's dates.
    Every row lands in exactly one split -- asserted, not assumed."""
    train = df[(df["game_date"] >= TRAIN_START) & (df["game_date"] <= TRAIN_END)]
    validation = df[(df["game_date"] >= VALIDATION_START) & (df["game_date"] <= VALIDATION_END)]
    test = df[(df["game_date"] >= TEST_START) & (df["game_date"] <= TEST_END)]
    assert len(train) + len(validation) + len(test) == len(df), (
        f"Chronological split does not partition the full dataset: "
        f"{len(train)}+{len(validation)}+{len(test)} != {len(df)} -- check for gaps/overlaps in the configured date ranges."
    )
    return train, validation, test


def build_dataset_summary(df: pd.DataFrame, train, validation, test) -> DatasetSummary:
    def _date_range(d):
        if len(d) == 0:
            return (None, None)
        return (d["game_date"].min(), d["game_date"].max())

    return DatasetSummary(
        total_rows=len(df), train_rows=len(train), validation_rows=len(validation), test_rows=len(test),
        train_dates=_date_range(train), validation_dates=_date_range(validation), test_dates=_date_range(test),
        unique_hitters=df["player_id"].nunique(), unique_games=df["game_pk"].nunique(), unique_teams=df["team"].nunique(),
    )


def missingness_by_family(df: pd.DataFrame, feature_columns) -> dict:
    from historical_models.hitter_v1.features import _family_of

    families: dict = {}
    for col in feature_columns:
        fam = _family_of(col)
        families.setdefault(fam, []).append(round(float(df[col].isna().mean()) * 100, 2))
    return {fam: round(sum(vals) / len(vals), 2) for fam, vals in families.items()}


def get_target(df: pd.DataFrame) -> pd.Series:
    return df[TARGET_COLUMN]


def target_distribution_summary(df: pd.DataFrame) -> dict:
    target = get_target(df)
    return {
        "mean": round(float(target.mean()), 3), "median": round(float(target.median()), 3),
        "std": round(float(target.std()), 3), "min": round(float(target.min()), 3), "max": round(float(target.max()), 3),
        "p10": round(float(target.quantile(0.10)), 3), "p25": round(float(target.quantile(0.25)), 3),
        "p50": round(float(target.quantile(0.50)), 3), "p75": round(float(target.quantile(0.75)), 3),
        "p90": round(float(target.quantile(0.90)), 3), "p95": round(float(target.quantile(0.95)), 3),
        "p99": round(float(target.quantile(0.99)), 3),
    }
