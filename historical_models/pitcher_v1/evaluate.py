"""Milestone 32.2 -- evaluation: primary metrics, DFS-specific metrics,
bucket analysis, calibration, outliers, feature importance. Pure
functions of (predictions, actuals, context) -- no training happens
here, so this module is safe to call standalone on a saved model's
predictions (python -m historical_models.pitcher_v1.evaluate).
"""

from typing import Dict, List

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import mean_absolute_error, median_absolute_error, r2_score, root_mean_squared_error


def compute_primary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    pearson_r, _ = pearsonr(y_true, y_pred) if len(y_true) > 1 else (float("nan"), None)
    spearman_r, _ = spearmanr(y_true, y_pred) if len(y_true) > 1 else (float("nan"), None)
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
        "rmse": round(float(root_mean_squared_error(y_true, y_pred)), 4),
        "pearson": round(float(pearson_r), 4),
        "spearman": round(float(spearman_r), 4),
        "bias": round(float(np.mean(y_pred - y_true)), 4),
        "median_absolute_error": round(float(median_absolute_error(y_true, y_pred)), 4),
        "r2": round(float(r2_score(y_true, y_pred)), 4),
        "n": int(len(y_true)),
    }


def compute_topn_metrics(df: pd.DataFrame, n: int, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> Dict[str, float]:
    """Per game_date: does the model's predicted top-N starting
    pitchers overlap with the ACTUAL top-N by real DK points? Averaged
    across every date with >= n starters."""
    overlaps, hit_flags, top_actual_avgs = [], [], []
    for _date, group in df.groupby("game_date"):
        if len(group) < n:
            continue
        predicted_top = set(group.nlargest(n, pred_col)["player_id"])
        actual_top = set(group.nlargest(n, actual_col)["player_id"])
        overlap = len(predicted_top & actual_top)
        overlaps.append(overlap / n)
        hit_flags.append(1 if overlap > 0 else 0)
        top_actual_avgs.append(group.nlargest(n, pred_col)[actual_col].mean())
    if not overlaps:
        return {"avg_overlap": None, "hit_rate": None, "top_projected_actual_avg": None, "dates_evaluated": 0}
    return {
        "avg_overlap": round(float(np.mean(overlaps)), 4),
        "hit_rate": round(float(np.mean(hit_flags)), 4),
        "top_projected_actual_avg": round(float(np.mean(top_actual_avgs)), 4),
        "dates_evaluated": len(overlaps),
    }


def compute_top_decile_actual_avg(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> float:
    threshold = df[pred_col].quantile(0.9)
    top_decile = df[df[pred_col] >= threshold]
    return round(float(top_decile[actual_col].mean()), 4) if len(top_decile) else None


def compute_calibration_table(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> List[dict]:
    bins = [-np.inf, 5, 10, 15, 20, 25, np.inf]
    labels = ["<5", "5-10", "10-15", "15-20", "20-25", "25+"]
    bucketed = pd.cut(df[pred_col], bins=bins, labels=labels, right=False)
    table = []
    for label in labels:
        subset = df[bucketed == label]
        if len(subset) == 0:
            table.append({"bucket": label, "count": 0, "avg_predicted": None, "avg_actual": None, "bias": None, "mae": None})
            continue
        avg_pred, avg_actual = subset[pred_col].mean(), subset[actual_col].mean()
        table.append({
            "bucket": label, "count": int(len(subset)),
            "avg_predicted": round(float(avg_pred), 2), "avg_actual": round(float(avg_actual), 2),
            "bias": round(float(avg_pred - avg_actual), 2),
            "mae": round(float((subset[pred_col] - subset[actual_col]).abs().mean()), 2),
        })
    return table


def _bucket_metric_rows(df: pd.DataFrame, group_col: str, pred_col: str, actual_col: str, min_n: int = 15) -> List[dict]:
    rows = []
    for value, group in df.groupby(group_col, observed=True):
        if len(group) < min_n:
            continue  # avoid over-fragmenting small samples
        m = compute_primary_metrics(group[actual_col].values, group[pred_col].values)
        rows.append({"bucket_value": str(value), "count": len(group), "mae": m["mae"], "bias": m["bias"]})
    return sorted(rows, key=lambda r: str(r["bucket_value"]))


def compute_bucket_analysis(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> Dict[str, List[dict]]:
    frame = df.copy()
    frame["_projection_range"] = pd.cut(
        frame[pred_col], bins=[-np.inf, 5, 10, 15, 20, 25, np.inf], labels=["<5", "5-10", "10-15", "15-20", "20-25", "25+"],
    )
    frame["_days_rest_bucket"] = pd.cut(frame["days_rest"], bins=[-np.inf, 3, 4, 5, 6, np.inf], labels=["<=3", "4", "5", "6", "7+"])
    frame["_opponent_k_bucket"] = pd.cut(
        frame["opponent_k_pct_season"], bins=[-np.inf, 0.20, 0.23, 0.26, np.inf], labels=["<20%", "20-23%", "23-26%", "26%+"],
    )
    frame["_statcast_available"] = frame["statcast_batted_balls_allowed_season"].notna() & (frame["statcast_batted_balls_allowed_season"] > 0)
    frame["_pitch_history_available"] = frame["previous_start_pitch_count"].notna()
    frame["_season_month"] = frame["game_date"].str.slice(0, 7)

    return {
        "projection_range": _bucket_metric_rows(frame, "_projection_range", pred_col, actual_col),
        "handedness": _bucket_metric_rows(frame, "throw_hand", pred_col, actual_col),
        "home_away": _bucket_metric_rows(frame, "home_away", pred_col, actual_col),
        "days_rest": _bucket_metric_rows(frame, "_days_rest_bucket", pred_col, actual_col),
        "opponent_k_rate": _bucket_metric_rows(frame, "_opponent_k_bucket", pred_col, actual_col),
        "statcast_available": _bucket_metric_rows(frame, "_statcast_available", pred_col, actual_col),
        "season_month": _bucket_metric_rows(frame, "_season_month", pred_col, actual_col),
        "pitch_history_available": _bucket_metric_rows(frame, "_pitch_history_available", pred_col, actual_col),
    }


_OUTLIER_FEATURE_COLS = [
    "rolling_k_pct_30d", "rolling_bb_pct_30d", "rolling_era_30d", "days_rest",
    "previous_start_pitch_count", "opponent_k_pct_season", "throw_hand", "home_away",
]


def compute_outliers(df: pd.DataFrame, n: int = 10, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> Dict[str, List[dict]]:
    frame = df.copy()
    frame["_error"] = frame[pred_col] - frame[actual_col]

    def _rows(sub):
        cols = ["game_date", "player_name", "team", "opponent", pred_col, actual_col, "_error"] + _OUTLIER_FEATURE_COLS
        return sub[cols].rename(columns={pred_col: "predicted", actual_col: "actual", "_error": "error"}).to_dict("records")

    over = frame.nlargest(n, "_error")
    under = frame.nsmallest(n, "_error")
    return {"largest_over_projections": _rows(over), "largest_under_projections": _rows(under)}


def compute_permutation_importance(pipeline, X: pd.DataFrame, y: pd.Series, seed: int, n_repeats: int = 8) -> List[dict]:
    from sklearn.inspection import permutation_importance

    result = permutation_importance(pipeline, X, y, n_repeats=n_repeats, random_state=seed, scoring="neg_mean_absolute_error", n_jobs=-1)
    rows = [
        {"feature": col, "importance_mean": round(float(m), 5), "importance_std": round(float(s), 5)}
        for col, m, s in zip(X.columns, result.importances_mean, result.importances_std)
    ]
    return sorted(rows, key=lambda r: -r["importance_mean"])
