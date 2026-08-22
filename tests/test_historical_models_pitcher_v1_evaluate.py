"""Milestone 32.2 -- evaluation metric tests: primary metrics, top-N DFS
metrics, calibration table, bucket analysis, outlier report, permutation
feature importance. All synthetic, deterministic inputs."""

import numpy as np
import pandas as pd

from historical_models.pitcher_v1.evaluate import (
    compute_bucket_analysis,
    compute_calibration_table,
    compute_outliers,
    compute_permutation_importance,
    compute_primary_metrics,
    compute_top_decile_actual_avg,
    compute_topn_metrics,
)
from historical_models.pitcher_v1.model import CANDIDATES, build_pipeline
from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS


def test_compute_primary_metrics_perfect_prediction_is_all_zero_error():
    y = np.array([10.0, 15.0, 20.0, 5.0])
    metrics = compute_primary_metrics(y, y.copy())
    assert metrics["mae"] == 0.0
    assert metrics["rmse"] == 0.0
    assert metrics["bias"] == 0.0
    assert metrics["median_absolute_error"] == 0.0
    assert metrics["r2"] == 1.0
    assert metrics["n"] == 4


def test_compute_primary_metrics_known_constant_bias():
    y_true = np.array([10.0, 20.0, 30.0])
    y_pred = y_true + 2.0  # every prediction over-projects by exactly 2
    metrics = compute_primary_metrics(y_true, y_pred)
    assert metrics["mae"] == 2.0
    assert metrics["bias"] == 2.0


def _topn_frame():
    return pd.DataFrame({
        "game_date": ["2025-09-01"] * 5 + ["2025-09-02"] * 3,
        "player_id": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"],
        "prediction": [30, 25, 20, 15, 10, 25, 20, 15],
        "actual_dk_points": [28, 26, 5, 18, 12, 22, 26, 10],
    })


def test_compute_topn_metrics_skips_dates_with_fewer_than_n_starters():
    df = _topn_frame()
    result = compute_topn_metrics(df, n=5)  # second date only has 3 rows
    assert result["dates_evaluated"] == 1


def test_compute_topn_metrics_overlap_and_hit_rate_bounds():
    df = _topn_frame()
    result = compute_topn_metrics(df, n=2)
    assert result["dates_evaluated"] == 2
    assert 0.0 <= result["avg_overlap"] <= 1.0
    assert 0.0 <= result["hit_rate"] <= 1.0


def test_compute_top_decile_actual_avg_uses_predicted_ranking():
    df = pd.DataFrame({"prediction": list(range(1, 11)), "actual_dk_points": list(range(1, 11))})
    result = compute_top_decile_actual_avg(df)
    assert result == 10.0  # only the single highest-predicted row qualifies at the 90th percentile


def test_compute_calibration_table_buckets_and_bias_direction():
    df = pd.DataFrame({"prediction": [7.0, 7.0, 22.0], "actual_dk_points": [5.0, 5.0, 25.0]})
    table = compute_calibration_table(df)
    bucket_5_10 = next(row for row in table if row["bucket"] == "5-10")
    assert bucket_5_10["count"] == 2
    assert bucket_5_10["bias"] > 0  # over-projected in this bucket

    bucket_20_25 = next(row for row in table if row["bucket"] == "20-25")
    assert bucket_20_25["bias"] < 0  # under-projected in this bucket

    empty_bucket = next(row for row in table if row["bucket"] == "25+")
    assert empty_bucket["count"] == 0
    assert empty_bucket["avg_predicted"] is None


def _bucket_analysis_frame(n=40, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "prediction": rng.uniform(0, 30, size=n),
        "actual_dk_points": rng.uniform(0, 30, size=n),
        "days_rest": rng.integers(3, 8, size=n),
        "opponent_k_pct_season": rng.uniform(0.15, 0.30, size=n),
        "statcast_batted_balls_allowed_season": rng.integers(0, 200, size=n),
        "previous_start_pitch_count": rng.uniform(60, 100, size=n),
        "throw_hand": rng.choice(["R", "L"], size=n),
        "home_away": rng.choice(["home", "away"], size=n),
        "game_date": [f"2025-{(i % 3) + 6:02d}-15" for i in range(n)],
    })


def test_compute_bucket_analysis_skips_small_buckets():
    df = _bucket_analysis_frame(n=40)
    result = compute_bucket_analysis(df)
    assert "handedness" in result
    for bucket_row in result["handedness"]:
        assert bucket_row["count"] >= 15  # min_n=15 enforced -- "avoid over-fragmenting small samples"


def test_compute_outliers_returns_correctly_sorted_over_and_under_projections():
    df = pd.DataFrame({
        "game_date": ["2025-09-01"] * 4,
        "player_name": ["A", "B", "C", "D"],
        "team": ["NYY", "BOS", "LAD", "CHC"],
        "opponent": ["BOS", "NYY", "CHC", "LAD"],
        "prediction": [20.0, 5.0, 15.0, 10.0],
        "actual_dk_points": [5.0, 20.0, 15.0, 10.0],
        "rolling_k_pct_30d": [0.2] * 4,
        "rolling_bb_pct_30d": [0.1] * 4,
        "rolling_era_30d": [3.5] * 4,
        "days_rest": [4] * 4,
        "previous_start_pitch_count": [90] * 4,
        "opponent_k_pct_season": [0.22] * 4,
        "throw_hand": ["R"] * 4,
        "home_away": ["home"] * 4,
    })
    outliers = compute_outliers(df, n=2)
    assert outliers["largest_over_projections"][0]["player_name"] == "A"  # +15 error, largest over-projection
    assert outliers["largest_under_projections"][0]["player_name"] == "B"  # -15 error, largest under-projection


def test_compute_permutation_importance_ranks_a_dominant_feature_highest():
    rng = np.random.default_rng(11)
    n = 60
    data = {col: rng.uniform(0, 1, size=n) for col in NUMERIC_FEATURE_COLUMNS}
    for col in CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["A", "B"], size=n)
    X = pd.DataFrame(data)

    dominant_col = NUMERIC_FEATURE_COLUMNS[0]
    y = pd.Series(X[dominant_col] * 100, name="actual_dk_points")  # target is (almost) purely a function of one feature

    spec = next(c for c in CANDIDATES if c.name == "random_forest")
    pipeline = build_pipeline(spec, {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2})
    pipeline.fit(X, y)

    importance = compute_permutation_importance(pipeline, X, y, seed=42, n_repeats=3)
    assert importance[0]["feature"] == dominant_col
