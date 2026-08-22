"""Milestone 32.2 -- preprocessing / candidate model tests for
historical_models.pitcher_v1.model. Covers: train-only imputation,
model-native missing-data handling for the raw/tree path, and
reproducibility under a fixed seed."""

import numpy as np
import pandas as pd

from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from historical_models.pitcher_v1.model import CANDIDATES, build_imputed_preprocessor, build_pipeline, build_raw_preprocessor


def _synthetic_X_y(n=40, seed=0, with_nans=True):
    rng = np.random.default_rng(seed)
    data = {col: rng.uniform(0, 10, size=n) for col in NUMERIC_FEATURE_COLUMNS}
    if with_nans:
        first_numeric = NUMERIC_FEATURE_COLUMNS[0]
        data[first_numeric][: n // 4] = np.nan  # first quarter of rows missing this one feature
    for col in CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["A", "B", "C"], size=n)
    X = pd.DataFrame(data)
    y = pd.Series(rng.uniform(0, 30, size=n), name="actual_dk_points")
    return X, y


def test_imputed_preprocessor_uses_train_statistics_only_not_validation():
    X_train, _ = _synthetic_X_y(n=40, seed=1)
    X_val, _ = _synthetic_X_y(n=10, seed=2)  # different distribution than train

    first_numeric = NUMERIC_FEATURE_COLUMNS[0]
    train_median = X_train[first_numeric].median()  # computed ignoring the injected NaNs, as pandas does

    preprocessor = build_imputed_preprocessor()
    preprocessor.fit(X_train)  # fit on TRAIN only
    X_val_with_hole = X_val.copy()
    X_val_with_hole.loc[0, first_numeric] = np.nan
    transformed = preprocessor.transform(X_val_with_hole)

    # The imputed value for the missing validation cell must equal TRAIN's
    # median, never validation's own median (which is a different sample).
    imputed_value = transformed[0, 0]
    assert np.isclose(imputed_value, train_median, atol=1e-6)


def test_raw_preprocessor_preserves_nan_for_tree_native_handling():
    X, _ = _synthetic_X_y(n=20, seed=3, with_nans=True)
    preprocessor = build_raw_preprocessor()
    preprocessor.fit(X)
    transformed = preprocessor.transform(X)
    first_numeric_idx = 0
    assert np.isnan(transformed[:, first_numeric_idx]).any(), "raw preprocessor must not fill NaN -- HistGradientBoostingRegressor needs it intact"


def test_hist_gradient_boosting_candidate_fits_directly_on_missing_values():
    X, y = _synthetic_X_y(n=40, seed=4, with_nans=True)
    spec = next(c for c in CANDIDATES if c.name == "hist_gradient_boosting")
    pipeline = build_pipeline(spec, spec.param_grid[0])
    pipeline.fit(X, y)  # must not raise despite NaN in X
    preds = pipeline.predict(X)
    assert len(preds) == len(X)


def test_imputed_candidates_fit_without_error_despite_missing_values():
    X, y = _synthetic_X_y(n=40, seed=5, with_nans=True)
    for spec in CANDIDATES:
        if spec.uses_raw_preprocessor:
            continue
        pipeline = build_pipeline(spec, spec.param_grid[0])
        pipeline.fit(X, y)
        preds = pipeline.predict(X)
        assert len(preds) == len(X)


def test_model_predictions_are_reproducible_under_fixed_seed():
    X, y = _synthetic_X_y(n=40, seed=6, with_nans=True)
    spec = next(c for c in CANDIDATES if c.name == "random_forest")
    params = spec.param_grid[0]

    pipeline_a = build_pipeline(spec, params)
    pipeline_a.fit(X, y)
    preds_a = pipeline_a.predict(X)

    pipeline_b = build_pipeline(spec, params)
    pipeline_b.fit(X, y)
    preds_b = pipeline_b.predict(X)

    assert np.allclose(preds_a, preds_b)


def test_mean_baseline_predicts_the_same_constant_for_every_row():
    X, y = _synthetic_X_y(n=15, seed=7, with_nans=False)
    spec = next(c for c in CANDIDATES if c.name == "mean_baseline")
    pipeline = build_pipeline(spec, spec.param_grid[0])
    pipeline.fit(X, y)
    preds = pipeline.predict(X)
    assert len(set(np.round(preds, 6))) == 1
    assert np.isclose(preds[0], y.mean(), atol=1e-6)


def test_one_hot_encoder_handles_unseen_category_without_raising():
    X_train, y_train = _synthetic_X_y(n=30, seed=8, with_nans=False)
    X_test, _ = _synthetic_X_y(n=5, seed=9, with_nans=False)
    X_test[CATEGORICAL_FEATURE_COLUMNS[0]] = "NEVER_SEEN_IN_TRAIN"

    spec = next(c for c in CANDIDATES if c.name == "ridge")
    pipeline = build_pipeline(spec, spec.param_grid[0])
    pipeline.fit(X_train, y_train)
    preds = pipeline.predict(X_test)  # must not raise
    assert len(preds) == len(X_test)
