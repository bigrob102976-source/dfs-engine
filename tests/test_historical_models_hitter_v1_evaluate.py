"""Milestone 32.3 -- evaluation metric tests: primary metrics, top-N DFS
metrics, ceiling recall, low-score analysis, calibration, batting-order/
platoon/park buckets, outliers, permutation feature importance. All
synthetic, deterministic inputs."""

import numpy as np
import pandas as pd

from historical_models.hitter_v1.evaluate import (
    compute_batting_order_analysis,
    compute_calibration_table,
    compute_ceiling_analysis,
    compute_low_score_analysis,
    compute_outliers,
    compute_park_analysis,
    compute_permutation_importance,
    compute_platoon_analysis,
    compute_primary_metrics,
    compute_top_decile_actual_avg,
    compute_topn_metrics,
)
from historical_models.hitter_v1.features import AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS
from historical_models.hitter_v1.model import CANDIDATES, build_pipeline


def test_compute_primary_metrics_perfect_prediction_is_all_zero_error():
    y = np.array([10.0, 15.0, 20.0, 5.0])
    metrics = compute_primary_metrics(y, y.copy())
    assert metrics["mae"] == 0.0
    assert metrics["r2"] == 1.0


def _topn_frame(n_per_date=25):
    rng = np.random.default_rng(0)
    rows = []
    for date in ("2025-09-01", "2025-09-02"):
        for i in range(n_per_date):
            rows.append({"game_date": date, "player_id": f"{date}-{i}", "prediction": rng.uniform(0, 20), "actual_dk_points": rng.uniform(0, 30)})
    return pd.DataFrame(rows)


def test_compute_topn_metrics_skips_dates_with_fewer_than_n_hitters():
    df = _topn_frame(n_per_date=3)
    result = compute_topn_metrics(df, n=5)
    assert result["dates_evaluated"] == 0


def test_compute_topn_metrics_overlap_bounds():
    df = _topn_frame(n_per_date=25)
    for n in (5, 10, 20):
        result = compute_topn_metrics(df, n=n)
        assert result["dates_evaluated"] == 2
        assert 0.0 <= result["avg_overlap"] <= 1.0
        assert 0.0 <= result["at_least_one_hit_rate"] <= 1.0


def test_compute_top_decile_actual_avg_uses_predicted_ranking():
    df = pd.DataFrame({"prediction": list(range(1, 11)), "actual_dk_points": list(range(1, 11))})
    assert compute_top_decile_actual_avg(df) == 10.0


def test_compute_calibration_table_hitter_scaled_buckets():
    df = pd.DataFrame({"prediction": [3.0, 3.0, 11.0], "actual_dk_points": [1.0, 1.0, 14.0]})
    table = compute_calibration_table(df)
    labels = [row["bucket"] for row in table]
    assert labels == ["<4", "4-6", "6-8", "8-10", "10-12", "12+"]
    bucket_lt4 = next(r for r in table if r["bucket"] == "<4")
    assert bucket_lt4["count"] == 2
    assert bucket_lt4["bias"] > 0


def test_compute_low_score_analysis_buckets_and_zero_bucket_isolated():
    df = pd.DataFrame({"prediction": [3.0, 2.0, 7.0, 15.0, 25.0], "actual_dk_points": [0.0, 3.0, 7.0, 15.0, 25.0]})
    rows = compute_low_score_analysis(df)
    by_bucket = {r["bucket"]: r for r in rows}
    assert by_bucket["0"]["n"] == 1
    assert by_bucket["0"]["avg_actual"] == 0.0
    assert by_bucket["0-5"]["n"] == 1
    assert by_bucket["5-10"]["n"] == 1
    assert by_bucket["10-20"]["n"] == 1
    assert by_bucket["20+"]["n"] == 1


def test_compute_ceiling_analysis_recall_structure():
    rng = np.random.default_rng(2)
    n = 60
    df = pd.DataFrame({
        "game_date": ["2025-09-01"] * n,
        "prediction": rng.uniform(0, 20, size=n),
        "actual_dk_points": rng.uniform(0, 40, size=n),
    })
    result = compute_ceiling_analysis(df, thresholds=(20,), top_fractions=(0.10,))
    assert "20+" in result
    entry = result["20+"]
    assert "n_qualifying_performances" in entry
    assert 0.0 <= entry["top_10pct_recall"] <= 1.0 or entry["top_10pct_recall"] is None


def test_compute_ceiling_analysis_perfect_predictor_has_full_recall():
    """If predicted == actual exactly, every qualifying ceiling
    performance must be in the top fraction of predictions too."""
    n = 50
    values = list(range(n))
    df = pd.DataFrame({"game_date": ["2025-09-01"] * n, "prediction": values, "actual_dk_points": values})
    result = compute_ceiling_analysis(df, thresholds=(40,), top_fractions=(0.20,))
    assert result["40+"]["top_20pct_recall"] == 1.0


def test_compute_batting_order_analysis_respects_min_n_and_sorts_by_order():
    rng = np.random.default_rng(3)
    rows = []
    for order in (1, 2, 3):
        for _ in range(20):
            rows.append({"batting_order_actual": order, "prediction": rng.uniform(0, 10), "actual_dk_points": rng.uniform(0, 10)})
    rows.append({"batting_order_actual": 9, "prediction": 5.0, "actual_dk_points": 5.0})  # only 1 row -- below min_n
    df = pd.DataFrame(rows)
    result = compute_batting_order_analysis(df, min_n=15)
    orders = [r["batting_order"] for r in result]
    assert orders == [1, 2, 3]  # sorted, order 9 dropped (n=1 < min_n)


def test_compute_platoon_analysis_builds_matchup_buckets():
    rng = np.random.default_rng(4)
    rows = []
    for bat_hand in ("L", "R"):
        for pitch_hand in ("L", "R"):
            for _ in range(20):
                rows.append({
                    "bat_hand": bat_hand, "opposing_starting_pitcher_hand": pitch_hand,
                    "prediction": rng.uniform(0, 10), "actual_dk_points": rng.uniform(0, 10),
                })
    df = pd.DataFrame(rows)
    result = compute_platoon_analysis(df, min_n=15)
    matchups = {r["matchup"] for r in result}
    assert matchups == {"L vs L", "L vs R", "R vs L", "R vs R"}


def test_compute_park_analysis_sorted_by_largest_bias():
    rng = np.random.default_rng(5)
    rows = []
    for venue, bias_shift in (("PARK_A", 0.0), ("PARK_B", 5.0)):
        for _ in range(20):
            actual = rng.uniform(0, 10)
            rows.append({"venue_id": venue, "prediction": actual + bias_shift, "actual_dk_points": actual})
    df = pd.DataFrame(rows)
    result = compute_park_analysis(df, min_n=15)
    assert result[0]["venue_id"] == "PARK_B"  # largest |bias| first


def test_compute_outliers_returns_correctly_sorted_over_and_under_projections():
    df = pd.DataFrame({
        "game_date": ["2025-09-01"] * 4, "player_name": ["A", "B", "C", "D"],
        "team": ["NYY", "BOS", "LAD", "CHC"], "opponent": ["BOS", "NYY", "CHC", "LAD"],
        "prediction": [20.0, 2.0, 10.0, 6.0], "actual_dk_points": [2.0, 20.0, 10.0, 6.0],
        "rolling_ops_30d": [0.8] * 4, "rolling_hr_per_pa_30d": [0.05] * 4,
        "platoon_vs_lhp_woba": [0.3] * 4, "platoon_vs_rhp_woba": [0.3] * 4,
        "opposing_starting_pitcher_hand": ["R"] * 4, "bat_hand": ["L"] * 4, "home_away": ["home"] * 4,
    })
    outliers = compute_outliers(df, n=2)
    assert outliers["largest_over_projections"][0]["player_name"] == "A"
    assert outliers["largest_under_projections"][0]["player_name"] == "B"


def test_compute_permutation_importance_ranks_a_dominant_feature_highest():
    rng = np.random.default_rng(11)
    n = 60
    data = {col: rng.uniform(0, 1, size=n) for col in AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS}
    for col in AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["A", "B"], size=n)
    X = pd.DataFrame(data)

    dominant_col = AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS[0]
    y = pd.Series(X[dominant_col] * 100, name="actual_dk_points")

    spec = next(c for c in CANDIDATES if c.name == "random_forest")
    pipeline = build_pipeline(spec, {"n_estimators": 50, "max_depth": 5, "min_samples_leaf": 2}, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS, AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS)
    pipeline.fit(X, y)

    importance = compute_permutation_importance(pipeline, X, y, seed=42, n_repeats=3)
    assert importance[0]["feature"] == dominant_col
