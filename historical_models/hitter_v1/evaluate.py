"""Milestone 32.3 -- evaluation: primary metrics, DFS-specific metrics,
ceiling identification, low-score analysis, calibration, batting-order/
platoon/park buckets, outliers, feature importance. Pure functions of
(predictions, actuals, context) -- no training happens here.
"""

from typing import Dict, List, Optional

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


def compute_topn_metrics(df: pd.DataFrame, n: int, pred_col: str = "prediction", actual_col: str = "actual_dk_points", date_col: str = "game_date") -> Dict[str, float]:
    """Per game_date: does the model's predicted top-N hitters overlap
    with the ACTUAL top-N by real DK points? Averaged across every date
    with >= n hitters."""
    overlaps, hit_flags, top_actual_avgs = [], [], []
    for _date, group in df.groupby(date_col):
        if len(group) < n:
            continue
        predicted_top = set(group.nlargest(n, pred_col)["player_id"])
        actual_top = set(group.nlargest(n, actual_col)["player_id"])
        overlap = len(predicted_top & actual_top)
        overlaps.append(overlap / n)
        hit_flags.append(1 if overlap > 0 else 0)
        top_actual_avgs.append(group.nlargest(n, pred_col)[actual_col].mean())
    if not overlaps:
        return {"avg_overlap": None, "at_least_one_hit_rate": None, "top_projected_actual_avg": None, "dates_evaluated": 0}
    return {
        "avg_overlap": round(float(np.mean(overlaps)), 4),
        "at_least_one_hit_rate": round(float(np.mean(hit_flags)), 4),
        "top_projected_actual_avg": round(float(np.mean(top_actual_avgs)), 4),
        "dates_evaluated": len(overlaps),
    }


def compute_top_decile_actual_avg(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> Optional[float]:
    threshold = df[pred_col].quantile(0.9)
    top_decile = df[df[pred_col] >= threshold]
    return round(float(top_decile[actual_col].mean()), 4) if len(top_decile) else None


def compute_calibration_table(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> List[dict]:
    bins = [-np.inf, 4, 6, 8, 10, 12, np.inf]
    labels = ["<4", "4-6", "6-8", "8-10", "10-12", "12+"]
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


def compute_low_score_analysis(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points") -> List[dict]:
    def _bucket(v: float) -> str:
        if v <= 0:
            return "0"
        if v < 5:
            return "0-5"
        if v < 10:
            return "5-10"
        if v < 20:
            return "10-20"
        return "20+"

    frame = df.copy()
    frame["_bucket"] = frame[actual_col].apply(_bucket)
    order = ["0", "0-5", "5-10", "10-20", "20+"]
    rows = []
    for label in order:
        subset = frame[frame["_bucket"] == label]
        if len(subset) == 0:
            rows.append({"bucket": label, "n": 0, "avg_predicted": None, "avg_actual": None, "bias": None, "mae": None})
            continue
        rows.append({
            "bucket": label, "n": int(len(subset)),
            "avg_predicted": round(float(subset[pred_col].mean()), 3), "avg_actual": round(float(subset[actual_col].mean()), 3),
            "bias": round(float((subset[pred_col] - subset[actual_col]).mean()), 3),
            "mae": round(float((subset[pred_col] - subset[actual_col]).abs().mean()), 3),
        })
    return rows


def _bucket_metric_rows(df: pd.DataFrame, group_col: str, pred_col: str, actual_col: str, min_n: int = 15) -> List[dict]:
    rows = []
    for value, group in df.groupby(group_col, observed=True):
        if len(group) < min_n:
            continue  # avoid over-fragmenting small samples
        m = compute_primary_metrics(group[actual_col].values, group[pred_col].values)
        rows.append({
            "bucket_value": str(value), "count": len(group), "mae": m["mae"], "bias": m["bias"],
            "avg_predicted": round(float(group[pred_col].mean()), 3), "avg_actual": round(float(group[actual_col].mean()), 3),
        })
    return sorted(rows, key=lambda r: str(r["bucket_value"]))


def compute_batting_order_analysis(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points", order_col: str = "batting_order_actual", min_n: int = 15) -> List[dict]:
    rows = _bucket_metric_rows(df, order_col, pred_col, actual_col, min_n=min_n)
    for r in rows:
        r["batting_order"] = int(float(r.pop("bucket_value")))
    return sorted(rows, key=lambda r: r["batting_order"])


def compute_platoon_analysis(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points", bat_hand_col: str = "bat_hand", pitcher_hand_col: str = "opposing_starting_pitcher_hand", min_n: int = 15) -> List[dict]:
    frame = df.copy()
    frame["_matchup"] = frame[bat_hand_col].astype(str) + " vs " + frame[pitcher_hand_col].astype(str)
    rows = _bucket_metric_rows(frame, "_matchup", pred_col, actual_col, min_n=min_n)
    for r in rows:
        r["matchup"] = r.pop("bucket_value")
    return rows


def compute_park_analysis(df: pd.DataFrame, pred_col: str = "prediction", actual_col: str = "actual_dk_points", venue_col: str = "venue_id", min_n: int = 15) -> List[dict]:
    rows = _bucket_metric_rows(df, venue_col, pred_col, actual_col, min_n=min_n)
    for r in rows:
        r["venue_id"] = r.pop("bucket_value")
    return sorted(rows, key=lambda r: -abs(r["bias"]))


def compute_ceiling_analysis(
    df: pd.DataFrame, thresholds=(20, 25, 30), top_fractions=(0.05, 0.10, 0.20),
    pred_col: str = "prediction", actual_col: str = "actual_dk_points", date_col: str = "game_date",
) -> Dict[str, dict]:
    """For each threshold (actual DK points >= threshold), what fraction
    of those genuine ceiling performances were in that SLATE's own
    top-5%/10%/20% of predictions (per-date percentile rank, not a
    season-wide rank -- a DFS lineup is built one slate at a time)."""
    results: Dict[str, dict] = {}
    top_sets: Dict[float, Dict[object, set]] = {frac: {} for frac in top_fractions}
    for date, group in df.groupby(date_col):
        n = len(group)
        for frac in top_fractions:
            k = max(1, int(round(frac * n)))
            top_sets[frac][date] = set(group.nlargest(k, pred_col).index)

    for threshold in thresholds:
        qualifying = df[df[actual_col] >= threshold]
        n_qualifying = len(qualifying)
        recall_by_fraction = {}
        for frac in top_fractions:
            if n_qualifying == 0:
                recall_by_fraction[f"top_{int(frac * 100)}pct_recall"] = None
                continue
            hits = sum(1 for idx, row in qualifying.iterrows() if idx in top_sets[frac].get(row[date_col], set()))
            recall_by_fraction[f"top_{int(frac * 100)}pct_recall"] = round(hits / n_qualifying, 4)
        results[f"{threshold}+"] = {"n_qualifying_performances": n_qualifying, **recall_by_fraction}
    return results


_OUTLIER_FEATURE_COLS = [
    "rolling_ops_30d", "rolling_hr_per_pa_30d", "platoon_vs_lhp_woba", "platoon_vs_rhp_woba",
    "opposing_starting_pitcher_hand", "bat_hand", "home_away",
]


def compute_outliers(df: pd.DataFrame, n: int = 20, pred_col: str = "prediction", actual_col: str = "actual_dk_points", has_batting_order: bool = False) -> Dict[str, List[dict]]:
    frame = df.copy()
    frame["_error"] = frame[pred_col] - frame[actual_col]

    context_cols = [c for c in _OUTLIER_FEATURE_COLS if c in frame.columns]
    cols = ["game_date", "player_name", "team", "opponent", pred_col, actual_col, "_error"] + context_cols
    if has_batting_order and "batting_order_actual" in frame.columns:
        cols.insert(4, "batting_order_actual")

    def _rows(sub):
        return sub[cols].rename(columns={pred_col: "predicted", actual_col: "actual", "_error": "error"}).to_dict("records")

    over = frame.nlargest(n, "_error")
    under = frame.nsmallest(n, "_error")
    return {"largest_over_projections": _rows(over), "largest_under_projections": _rows(under)}


def compute_permutation_importance(pipeline, X: pd.DataFrame, y: pd.Series, seed: int, n_repeats: int = 5) -> List[dict]:
    from sklearn.inspection import permutation_importance

    result = permutation_importance(pipeline, X, y, n_repeats=n_repeats, random_state=seed, scoring="neg_mean_absolute_error", n_jobs=-1)
    rows = [
        {"feature": col, "importance_mean": round(float(m), 5), "importance_std": round(float(s), 5)}
        for col, m, s in zip(X.columns, result.importances_mean, result.importances_std)
    ]
    return sorted(rows, key=lambda r: -r["importance_mean"])
