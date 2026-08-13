"""Grades a pregame prediction snapshot against actual (postgame)
results. Pure computation -- no network, no file I/O (callers load the
snapshot and results JSON and hand them in as plain dicts/lists).

This module is the ONLY place ranking/error/correlation math for
evaluation lives. It never writes back into a snapshot (snapshots are
immutable) and never touches agents/pitcher_agent.py or its config --
see config/evaluation_config.py's docstring for why that separation
matters this milestone.

Only pitchers whose actual result status is in
config.evaluation_config.ACCURACY_ELIGIBLE_STATUSES (currently just
"completed_start") count toward MAE/RMSE/correlation/rank/hit-rate/
bucket metrics. Every other pitcher is still preserved in `records` with
their real status, just excluded from those metrics and reported
separately in `status_breakdown`.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config import evaluation_config as eval_cfg

# ----------------------------------------------------------------------------
# Small numeric helpers
# ----------------------------------------------------------------------------


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


def _variance(values: List[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    return round(sum((v - m) ** 2 for v in values) / len(values), 3)


def _pearson_correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None  # a constant series has no defined correlation
    return round(cov / ((var_x ** 0.5) * (var_y ** 0.5)), 4)


def _bucket_label(value: Optional[float], buckets: List[dict]) -> Optional[str]:
    if value is None:
        return None
    for b in buckets:
        if b["low"] <= value < b["high"]:
            return b["label"]
    return None


# ----------------------------------------------------------------------------
# Join snapshot predictions with actual results
# ----------------------------------------------------------------------------


def _build_records(snapshot: dict, actual_results: List[dict]) -> List[dict]:
    actuals_by_key = {(str(r["player_id"]), str(r.get("game_id"))): r for r in actual_results}

    records = []
    for pred in snapshot["pitchers"]:
        key = (str(pred["player_id"]), str(pred.get("game_id")))
        actual = actuals_by_key.get(key)

        status = actual["status"] if actual else "missing_result"
        actual_points = actual.get("dfs_points") if actual else None
        eligible = status in eval_cfg.ACCURACY_ELIGIBLE_STATUSES and actual_points is not None

        projection = pred.get("projection")
        error = abs_error = squared_error = None
        ceiling_hit = floor_miss = None
        if eligible and projection is not None:
            error = round(actual_points - projection, 2)
            abs_error = round(abs(error), 2)
            squared_error = round(error * error, 3)
            ceiling = pred.get("ceiling")
            floor = pred.get("floor")
            ceiling_hit = actual_points >= ceiling if ceiling is not None else None
            floor_miss = actual_points < floor if floor is not None else None
        elif status not in eval_cfg.ACCURACY_ELIGIBLE_STATUSES:
            eligible = False

        records.append({
            "player_id": pred["player_id"],
            "name": pred.get("name"),
            "team": pred.get("team"),
            "opponent": pred.get("opponent"),
            "status": status,
            "eligible": eligible,
            "projection": projection,
            "ceiling": pred.get("ceiling"),
            "floor": pred.get("floor"),
            "overall_score": pred.get("overall_score"),
            "risk_score": pred.get("risk_score"),
            "confidence": pred.get("confidence"),
            "tags": pred.get("tags") or [],
            "actual_dfs_points": actual_points,
            "error": error,
            "abs_error": abs_error,
            "squared_error": squared_error,
            "ceiling_hit": ceiling_hit,
            "floor_miss": floor_miss,
            "predicted_rank": None,
            "actual_rank": None,
            "rank_error": None,
        })
    return records


def _assign_ranks(records: List[dict]) -> None:
    """Predicted rank is by PROJECTION (our DK-points estimate), actual
    rank is by actual DK points -- both computed only among eligible
    (completed_start) pitchers, so a scratch never distorts the ranking
    of pitchers who actually played. Mutates `records` in place."""
    eligible = [r for r in records if r["eligible"]]
    by_projection = sorted(eligible, key=lambda r: -r["projection"])
    by_actual = sorted(eligible, key=lambda r: -r["actual_dfs_points"])
    predicted_rank = {r["player_id"]: i + 1 for i, r in enumerate(by_projection)}
    actual_rank = {r["player_id"]: i + 1 for i, r in enumerate(by_actual)}

    for r in records:
        r["predicted_rank"] = predicted_rank.get(r["player_id"])
        r["actual_rank"] = actual_rank.get(r["player_id"])
        if r["predicted_rank"] is not None and r["actual_rank"] is not None:
            # Positive = finished WORSE than predicted (higher rank number);
            # negative = finished BETTER than predicted. Matches the
            # milestone's own worked example exactly.
            r["rank_error"] = r["actual_rank"] - r["predicted_rank"]


# ----------------------------------------------------------------------------
# Slate-level metrics
# ----------------------------------------------------------------------------


def _slate_metrics(eligible: List[dict]) -> dict:
    n = len(eligible)
    mae = _mean([r["abs_error"] for r in eligible])
    rmse = round((sum(r["squared_error"] for r in eligible) / n) ** 0.5, 3) if n else None
    projection_corr = _pearson_correlation([r["projection"] for r in eligible], [r["actual_dfs_points"] for r in eligible])
    overall_corr = _pearson_correlation(
        [r["overall_score"] for r in eligible if r["overall_score"] is not None],
        [r["actual_dfs_points"] for r in eligible if r["overall_score"] is not None],
    )
    ceiling_hits = [r for r in eligible if r["ceiling_hit"]]
    floor_misses = [r for r in eligible if r["floor_miss"]]
    return {
        "pitchers_evaluated": n,
        "mae": mae,
        "rmse": rmse,
        "projection_correlation": projection_corr,
        "overall_score_correlation": overall_corr,
        "ceiling_hit_rate": round(len(ceiling_hits) / n, 3) if n else None,
        "floor_miss_rate": round(len(floor_misses) / n, 3) if n else None,
    }


def _hit_rate(eligible: List[dict], n: int) -> Optional[float]:
    if len(eligible) < n:
        return None
    predicted_top = {r["player_id"] for r in sorted(eligible, key=lambda r: -r["projection"])[:n]}
    actual_top = {r["player_id"] for r in sorted(eligible, key=lambda r: -r["actual_dfs_points"])[:n]}
    return round(len(predicted_top & actual_top) / n, 3)


def _risk_bucket_summary(eligible: List[dict]) -> List[dict]:
    summary = []
    for bucket in eval_cfg.RISK_BUCKETS:
        group = [r for r in eligible if _bucket_label(r["risk_score"], eval_cfg.RISK_BUCKETS) == bucket["label"]]
        n = len(group)
        points = [r["actual_dfs_points"] for r in group]
        summary.append({
            "bucket": bucket["label"],
            "count": n,
            "avg_actual_dfs_points": _mean(points),
            "variance": _variance(points),
            "bust_rate": round(sum(1 for r in group if r["floor_miss"]) / n, 3) if n else None,
            "ceiling_hit_rate": round(sum(1 for r in group if r["ceiling_hit"]) / n, 3) if n else None,
        })
    return summary


def _confidence_bucket_summary(eligible: List[dict]) -> List[dict]:
    summary = []
    for bucket in eval_cfg.CONFIDENCE_BUCKETS:
        group = [r for r in eligible if _bucket_label(r["confidence"], eval_cfg.CONFIDENCE_BUCKETS) == bucket["label"]]
        n = len(group)
        summary.append({
            "bucket": bucket["label"],
            "count": n,
            "mae": _mean([r["abs_error"] for r in group]),
            "avg_error": _mean([r["error"] for r in group]),
        })
    return summary


def _tag_performance(eligible: List[dict]) -> List[dict]:
    tags = sorted({tag for r in eligible for tag in r["tags"]})
    performance = []
    for tag in tags:
        group = [r for r in eligible if tag in r["tags"]]
        n = len(group)
        performance.append({
            "tag": tag,
            "count": n,
            "avg_projected_dfs_points": _mean([r["projection"] for r in group]),
            "avg_actual_dfs_points": _mean([r["actual_dfs_points"] for r in group]),
            "avg_error": _mean([r["error"] for r in group]),
            "avg_actual_rank": _mean([r["actual_rank"] for r in group if r["actual_rank"] is not None]),
        })
    return performance


def _top_n_by(eligible: List[dict], key: str, n: int) -> List[dict]:
    return sorted(eligible, key=lambda r: -r[key])[:n]


def _best_worst_calls(eligible: List[dict], n: int) -> Tuple[List[dict], List[dict]]:
    ranked = [r for r in eligible if r["rank_error"] is not None]
    by_abs_rank_error = sorted(ranked, key=lambda r: abs(r["rank_error"]))
    best = by_abs_rank_error[:n]
    worst = list(reversed(by_abs_rank_error[-n:])) if by_abs_rank_error else []
    return best, worst


def _surprises_and_busts(eligible: List[dict], n: int) -> Tuple[List[dict], List[dict]]:
    scored = [r for r in eligible if r["error"] is not None]
    by_error_desc = sorted(scored, key=lambda r: -r["error"])
    positive_surprises = by_error_desc[:n]
    busts = list(reversed(by_error_desc[-n:])) if by_error_desc else []
    return positive_surprises, busts


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


@dataclass
class EvaluationReport:
    slate_date: str
    model_version: str
    generated_at: str
    snapshot_generated_at: str
    snapshot_path: Optional[str]

    pitcher_count_predicted: int
    status_breakdown: Dict[str, int]

    slate_metrics: dict
    top5_hit_rate: Optional[float]
    top10_hit_rate: Optional[float]

    top_predicted: List[dict]
    top_actual: List[dict]
    best_calls: List[dict]
    worst_calls: List[dict]
    biggest_positive_surprises: List[dict]
    biggest_busts: List[dict]

    risk_bucket_summary: List[dict]
    confidence_bucket_summary: List[dict]
    tag_performance: List[dict]

    records: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_slate(snapshot: dict, actual_results: List[dict], snapshot_path: Optional[str] = None) -> EvaluationReport:
    records = _build_records(snapshot, actual_results)
    _assign_ranks(records)
    eligible = [r for r in records if r["eligible"]]

    status_breakdown: Dict[str, int] = {}
    for r in records:
        status_breakdown[r["status"]] = status_breakdown.get(r["status"], 0) + 1

    slate_metrics = _slate_metrics(eligible)
    best_calls, worst_calls = _best_worst_calls(eligible, eval_cfg.BEST_WORST_CALL_COUNT)
    positive_surprises, busts = _surprises_and_busts(eligible, eval_cfg.SURPRISE_BUST_COUNT)

    return EvaluationReport(
        slate_date=snapshot["slate_date"],
        model_version=snapshot.get("model_version", "unknown"),
        generated_at=datetime.now(timezone.utc).isoformat(),
        snapshot_generated_at=snapshot.get("generated_at", ""),
        snapshot_path=snapshot_path,
        pitcher_count_predicted=len(records),
        status_breakdown=status_breakdown,
        slate_metrics=slate_metrics,
        top5_hit_rate=_hit_rate(eligible, 5),
        top10_hit_rate=_hit_rate(eligible, 10),
        top_predicted=_top_n_by(eligible, "projection", max(eval_cfg.TOP_N_HIT_RATES, default=10)),
        top_actual=_top_n_by(eligible, "actual_dfs_points", max(eval_cfg.TOP_N_HIT_RATES, default=10)),
        best_calls=best_calls,
        worst_calls=worst_calls,
        biggest_positive_surprises=positive_surprises,
        biggest_busts=busts,
        risk_bucket_summary=_risk_bucket_summary(eligible),
        confidence_bucket_summary=_confidence_bucket_summary(eligible),
        tag_performance=_tag_performance(eligible),
        records=records,
    )
