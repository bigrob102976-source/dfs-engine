"""Milestone 32.3 -- candidate models + preprocessing. Mirrors
historical_models.pitcher_v1.model exactly (same dual-preprocessing-path
discipline, same missing-data instruction), parameterized by
numeric/categorical column lists so the SAME candidate specs serve both
the ALWAYS_PREGAME and AFTER_LINEUP feature-availability experiments
(config.ALWAYS_PREGAME / config.AFTER_LINEUP) without duplicating the
model definitions.

Two preprocessing paths:

  IMPUTED  -- median imputation (+ missingness indicator columns) for
              numeric features, fit on TRAIN ONLY. Used by Mean, Ridge,
              RandomForestRegressor, ExtraTreesRegressor.
  RAW      -- numeric features passed through untouched (NaN preserved).
              Used by HistGradientBoostingRegressor, which natively
              splits on missing values.

No hyperparameter search library is used -- each candidate gets a
small, hand-picked grid, scored ONCE against the VALIDATION set (never
cross-validated, since k-fold CV would shuffle across chronology).
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from historical_models.hitter_v1.config import DEFAULT_SEED


def build_imputed_preprocessor(numeric_columns: List[str], categorical_columns: List[str]) -> ColumnTransformer:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median", add_indicator=True))])
    categorical = OneHotEncoder(handle_unknown="ignore")
    return ColumnTransformer([("num", numeric, numeric_columns), ("cat", categorical, categorical_columns)])


def build_raw_preprocessor(numeric_columns: List[str], categorical_columns: List[str]) -> ColumnTransformer:
    categorical = OneHotEncoder(handle_unknown="ignore")
    return ColumnTransformer([("num", "passthrough", numeric_columns), ("cat", categorical, categorical_columns)])


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
            {"n_estimators": 200, "max_depth": 6, "min_samples_leaf": 20},
            {"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 10},
        ],
        build_estimator=lambda **p: RandomForestRegressor(random_state=DEFAULT_SEED, n_jobs=-1, **p),
    ),
    CandidateSpec(
        name="extra_trees", uses_raw_preprocessor=False,
        param_grid=[
            {"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 10},
        ],
        build_estimator=lambda **p: ExtraTreesRegressor(random_state=DEFAULT_SEED, n_jobs=-1, **p),
    ),
    CandidateSpec(
        name="hist_gradient_boosting", uses_raw_preprocessor=True,
        param_grid=[
            {"max_depth": 3, "learning_rate": 0.05, "max_iter": 200},
            {"max_depth": 6, "learning_rate": 0.05, "max_iter": 200},
            {"max_depth": 6, "learning_rate": 0.1, "max_iter": 150},
        ],
        build_estimator=lambda **p: HistGradientBoostingRegressor(random_state=DEFAULT_SEED, **p),
    ),
]


def build_pipeline(spec: CandidateSpec, params: Dict[str, Any], numeric_columns: List[str], categorical_columns: List[str]) -> Pipeline:
    preprocessor = (
        build_raw_preprocessor(numeric_columns, categorical_columns) if spec.uses_raw_preprocessor
        else build_imputed_preprocessor(numeric_columns, categorical_columns)
    )
    return Pipeline([("preprocess", preprocessor), ("estimator", spec.build_estimator(**params))])
