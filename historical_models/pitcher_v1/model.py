"""Milestone 32.2 -- candidate models + preprocessing.

Two preprocessing paths, per this milestone's explicit missing-data
instruction ("For tree models: allow model-native missing handling
where supported. For linear models: impute using TRAIN-SET statistics
only."):

  IMPUTED  -- median imputation (+ missingness indicator columns) for
              numeric features, fit on TRAIN ONLY. Used by Mean, Ridge,
              RandomForestRegressor, ExtraTreesRegressor -- none of
              sklearn's standard RF/ET/linear estimators accept NaN.
  RAW      -- numeric features passed through untouched (NaN preserved).
              Used by HistGradientBoostingRegressor, which natively
              splits on missing values.

Both paths one-hot categorical features identically (fit on TRAIN only,
unknown categories at val/test time map to all-zero, never an error).

No hyperparameter search library is used -- per this milestone's "do
not launch massive hyperparameter search" instruction, each candidate
gets a small, hand-picked grid, and every combination is scored ONCE
against the VALIDATION set (never cross-validated, since k-fold CV
would shuffle across chronology and violate the time-based-split rule
this whole package exists to enforce).
"""

from dataclasses import dataclass
from typing import Any, Dict, List

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from historical_models.pitcher_v1.config import DEFAULT_SEED
from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS


def build_imputed_preprocessor() -> ColumnTransformer:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True))])
    categorical = OneHotEncoder(handle_unknown="ignore")
    return ColumnTransformer([("num", numeric, NUMERIC_FEATURE_COLUMNS), ("cat", categorical, CATEGORICAL_FEATURE_COLUMNS)])


def build_raw_preprocessor() -> ColumnTransformer:
    categorical = OneHotEncoder(handle_unknown="ignore")
    return ColumnTransformer([("num", "passthrough", NUMERIC_FEATURE_COLUMNS), ("cat", categorical, CATEGORICAL_FEATURE_COLUMNS)])


@dataclass
class CandidateSpec:
    name: str
    uses_raw_preprocessor: bool  # True only for HistGradientBoostingRegressor
    param_grid: List[Dict[str, Any]]
    build_estimator: Any  # callable(**params) -> sklearn estimator


CANDIDATES: List[CandidateSpec] = [
    CandidateSpec(
        name="mean_baseline", uses_raw_preprocessor=False, param_grid=[{}],
        build_estimator=lambda **_: DummyRegressor(strategy="mean"),
    ),
    CandidateSpec(
        name="ridge", uses_raw_preprocessor=False,
        param_grid=[{"alpha": a} for a in (0.1, 1.0, 10.0, 100.0)],
        build_estimator=lambda **p: Ridge(random_state=DEFAULT_SEED, **p),
    ),
    CandidateSpec(
        name="random_forest", uses_raw_preprocessor=False,
        param_grid=[
            {"n_estimators": 300, "max_depth": 6, "min_samples_leaf": 10},
            {"n_estimators": 300, "max_depth": 10, "min_samples_leaf": 5},
            {"n_estimators": 300, "max_depth": None, "min_samples_leaf": 5},
        ],
        build_estimator=lambda **p: RandomForestRegressor(random_state=DEFAULT_SEED, n_jobs=-1, **p),
    ),
    CandidateSpec(
        name="extra_trees", uses_raw_preprocessor=False,
        param_grid=[
            {"n_estimators": 300, "max_depth": 10, "min_samples_leaf": 5},
            {"n_estimators": 300, "max_depth": None, "min_samples_leaf": 5},
        ],
        build_estimator=lambda **p: ExtraTreesRegressor(random_state=DEFAULT_SEED, n_jobs=-1, **p),
    ),
    CandidateSpec(
        name="hist_gradient_boosting", uses_raw_preprocessor=True,
        param_grid=[
            {"max_depth": 3, "learning_rate": 0.05, "max_iter": 300},
            {"max_depth": 6, "learning_rate": 0.05, "max_iter": 300},
            {"max_depth": 6, "learning_rate": 0.1, "max_iter": 200},
        ],
        build_estimator=lambda **p: HistGradientBoostingRegressor(random_state=DEFAULT_SEED, **p),
    ),
]


def build_pipeline(spec: CandidateSpec, params: Dict[str, Any]) -> Pipeline:
    preprocessor = build_raw_preprocessor() if spec.uses_raw_preprocessor else build_imputed_preprocessor()
    return Pipeline([("preprocess", preprocessor), ("estimator", spec.build_estimator(**params))])
