"""Milestone 32.2 -- load the warehouse, filter to starting pitchers,
apply the chronological split. No model logic here -- this module is
pure data loading/filtering/splitting, kept separate so it's testable
without touching sklearn at all.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from historical_models.pitcher_v1.config import (
    DEFAULT_WAREHOUSE_PITCHER_PARQUET, TARGET_COLUMN, TEST_END, TEST_START,
    TRAIN_END, TRAIN_START, VALIDATION_END, VALIDATION_START,
)


@dataclass
class DatasetSummary:
    total_rows: int
    excluded_relief_rows: int
    retained_starter_rows: int
    train_rows: int
    validation_rows: int
    test_rows: int
    train_dates: tuple
    validation_dates: tuple
    test_dates: tuple


def load_starting_pitcher_dataset(parquet_path: Optional[Path] = None) -> pd.DataFrame:
    """Loads pitcher_game_features.parquet and filters to
    starter_flag == True (the warehouse's authoritative starting-pitcher
    indicator -- see historical_mlb.pitcher_features.build_pitcher_game_row,
    which sets it directly from the box score's own gamesStarted field).
    Relievers are excluded entirely, per this milestone's explicit
    "Do not train on relievers" instruction."""
    path = parquet_path or DEFAULT_WAREHOUSE_PITCHER_PARQUET
    df = pd.read_parquet(path)
    starters = df[df["starter_flag"] == True].copy()  # noqa: E712 -- explicit bool comparison reads clearer here than `df["starter_flag"]`
    starters = starters.sort_values(["game_date", "game_pk", "player_id"]).reset_index(drop=True)
    return starters


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


def build_dataset_summary(all_pitcher_rows: pd.DataFrame, starters: pd.DataFrame, train, validation, test) -> DatasetSummary:
    def _date_range(d):
        if len(d) == 0:
            return (None, None)
        return (d["game_date"].min(), d["game_date"].max())

    return DatasetSummary(
        total_rows=len(all_pitcher_rows),
        excluded_relief_rows=len(all_pitcher_rows) - len(starters),
        retained_starter_rows=len(starters),
        train_rows=len(train), validation_rows=len(validation), test_rows=len(test),
        train_dates=_date_range(train), validation_dates=_date_range(validation), test_dates=_date_range(test),
    )


def missingness_by_family(df: pd.DataFrame) -> dict:
    from historical_models.pitcher_v1.features import FEATURE_COLUMNS, _family_of

    families: dict = {}
    for col in FEATURE_COLUMNS:
        fam = _family_of(col)
        families.setdefault(fam, []).append(round(float(df[col].isna().mean()) * 100, 2))
    return {fam: round(sum(vals) / len(vals), 2) for fam, vals in families.items()}


def get_target(df: pd.DataFrame) -> pd.Series:
    return df[TARGET_COLUMN]
