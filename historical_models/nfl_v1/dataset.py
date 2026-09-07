"""NFL M10 -- loads the real M9 training dataset (Parquet) and builds
per-position feature matrices / target vectors for model training.

Feature set (v1, deliberately bounded -- see this milestone's own scope
decisions): every numeric key from M9's rolling_features and
season_to_date_features dicts, plus weeks_of_history, has_prior_week (as
0/1), home_away (as 1/0/NaN), rest_days. Team/opponent/injury_report_
status categorical encoding is explicitly OUT of v1's scope (documented,
not fabricated) -- salary and Vegas are never used (M9 leaves them None
for every row; a model trained on an always-null column would just
learn to ignore it, but including them at all would misleadingly imply
they're real inputs).

`recent_dk_points_mean_last3` (Phase 2's baseline B) is computed HERE,
not stored in M9's Parquet files, from the real per-row target values
across ALL rows (train+validation+test) -- reading a player's OWN past
weeks' real, already-happened target values to predict a LATER week is
not leakage (that later week's own target is never read for itself);
this mirrors exactly the same trailing-window discipline historical_nfl/
usage_rolling.py already uses for every other feature.
"""

import glob
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import polars as pl

from historical_models.nfl_v1.config import DST_POSITION, OFFENSE_POSITIONS, SPLIT_TEST, SPLIT_TRAIN, SPLIT_VALIDATION, TARGET_COLUMN


def latest_dataset_dir(training_root: Path) -> Path:
    """Newest {season}/{timestamp}/ snapshot under M9's persisted
    training root, by directory name (timestamps sort chronologically)."""
    candidates = sorted(glob.glob(str(training_root / "*" / "*")))
    if not candidates:
        raise FileNotFoundError(f"No M9 training dataset found under {training_root}")
    return Path(candidates[-1])


def _load_split(dataset_dir: Path, split: str, kind: str) -> pd.DataFrame:
    path = dataset_dir / f"{split}_{kind}.parquet"
    df = pl.read_parquet(path).to_pandas()
    for col in ("rolling_features", "season_to_date_features"):
        if col in df.columns:
            df[col] = df[col].apply(lambda s: json.loads(s) if isinstance(s, str) and s else {})
    return df


def load_all_splits(dataset_dir: Path, kind: str) -> Dict[str, pd.DataFrame]:
    return {split: _load_split(dataset_dir, split, kind) for split in (SPLIT_TRAIN, SPLIT_VALIDATION, SPLIT_TEST)}


def _flatten_features(row: pd.Series, feature_keys: List[str]) -> Dict[str, Optional[float]]:
    rolling = row.get("rolling_features") or {}
    std = row.get("season_to_date_features") or {}
    merged = {**rolling, **std}
    out = {k: merged.get(k) for k in feature_keys}
    out["weeks_of_history"] = row.get("weeks_of_history")
    out["has_prior_week"] = 1.0 if row.get("has_prior_week") else 0.0
    home_away = row.get("home_away")
    out["is_home"] = 1.0 if home_away == "home" else (0.0 if home_away == "away" else np.nan)
    if "rest_days" in row.index:
        out["rest_days"] = row.get("rest_days")
    return out


def discover_feature_keys(df: pd.DataFrame) -> List[str]:
    keys = set()
    for col in ("rolling_features", "season_to_date_features"):
        if col in df.columns:
            for d in df[col]:
                if isinstance(d, dict):
                    keys.update(k for k in d.keys() if k != "weeks_of_history")
    return sorted(keys)


def add_recent_dk_points_feature(splits: Dict[str, pd.DataFrame], id_col: str) -> Dict[str, pd.DataFrame]:
    """Leakage-safe trailing mean of the player/team's own REAL, already-
    observed target values from strictly earlier weeks -- see module
    docstring. Computed once across all three splits combined (their
    union is exactly "every real row this season"), then the per-split
    frames are returned with the new column attached."""
    combined = pd.concat([splits[SPLIT_TRAIN], splits[SPLIT_VALIDATION], splits[SPLIT_TEST]], ignore_index=True)
    history: Dict[str, List[Tuple[int, float]]] = {}
    for _, row in combined.sort_values(["week"]).iterrows():
        key = row[id_col]
        history.setdefault(key, [])

    values_by_key: Dict[str, Dict[int, float]] = {}
    for _, row in combined.iterrows():
        key = row[id_col]
        week = row["week"]
        target = row[TARGET_COLUMN]
        if target is not None:
            values_by_key.setdefault(key, {})[week] = target

    def recent_mean(key, week, window=3):
        weeks_map = values_by_key.get(key, {})
        vals = [weeks_map[w] for w in range(week - window, week) if w in weeks_map]
        return float(np.mean(vals)) if vals else np.nan

    out = {}
    for split, df in splits.items():
        df = df.copy()
        df["recent_dk_points_mean_last3"] = [recent_mean(row[id_col], row["week"]) for _, row in df.iterrows()]
        out[split] = df
    return out


def build_position_arrays(splits: Dict[str, pd.DataFrame], position: str) -> Dict[str, dict]:
    """Returns {split: {"X": DataFrame, "y": Series, "meta": DataFrame}}
    for one offense position (QB/RB/WR/TE). `meta` carries identifying
    columns (gsis_id/season/week/team/opponent/weeks_of_history) for
    error analysis, never fed to the model."""
    all_keys = sorted(set().union(*[discover_feature_keys(df) for df in splits.values()]))
    result = {}
    for split, df in splits.items():
        pos_df = df[df["position"] == position].reset_index(drop=True)
        feature_rows = [_flatten_features(row, all_keys) for _, row in pos_df.iterrows()]
        X = pd.DataFrame(feature_rows)
        if "recent_dk_points_mean_last3" in pos_df.columns:
            X["recent_dk_points_mean_last3"] = pos_df["recent_dk_points_mean_last3"].to_numpy()
        y = pos_df[TARGET_COLUMN]
        meta = pos_df[["gsis_id", "season", "week", "team", "opponent", "weeks_of_history"]]
        result[split] = {"X": X, "y": y, "meta": meta}
    return result


def build_dst_arrays(splits: Dict[str, pd.DataFrame]) -> Dict[str, dict]:
    all_keys = sorted(set().union(*[discover_feature_keys(df) for df in splits.values()]))
    result = {}
    for split, df in splits.items():
        feature_rows = []
        for _, row in df.iterrows():
            rolling = row.get("rolling_features") or {}
            out = {k: rolling.get(k) for k in all_keys}
            out["weeks_of_history"] = row.get("weeks_of_history")
            out["has_prior_week"] = 1.0 if row.get("has_prior_week") else 0.0
            home_away = row.get("home_away")
            out["is_home"] = 1.0 if home_away == "home" else (0.0 if home_away == "away" else np.nan)
            feature_rows.append(out)
        X = pd.DataFrame(feature_rows)
        if "recent_dk_points_mean_last3" in df.columns:
            X["recent_dk_points_mean_last3"] = df["recent_dk_points_mean_last3"].to_numpy()
        y = df[TARGET_COLUMN]
        meta = df[["team", "season", "week", "opponent", "weeks_of_history"]]
        result[split] = {"X": X, "y": y, "meta": meta}
    return result
