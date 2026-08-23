"""Pure metric math for comparing multiple projection SOURCES (external
baseline / Big Money independent / Big Money adjusted / AI Projection)
against actual results, once a slate has both actual results AND those
projections recorded for it.

Wired into a live script by scripts/run_projection_source_comparison.py
and evaluation/projection_source_loader.py (which reads the real
snapshots and builds the {player_id: value} maps this module expects).
This module itself stays IO-free and source-agnostic on purpose. Like
evaluation/pitcher_evaluator.py, any real use of this module must only
ever compare a PREGAME snapshot against POSTGAME results collected
after that snapshot was taken.

Reuses the exact MAE/RMSE/Pearson-correlation math
evaluation/pitcher_evaluator.py already uses, generalized to accept
plain {player_id: value} maps instead of pitcher-specific fields, so
results computed with this module are directly comparable to existing
pitcher evaluation reports. Also adds Spearman rank correlation and a
top-N hit rate, both explicitly requested by the milestone.
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 3) if values else None


def _pearson_correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return round(cov / ((var_x ** 0.5) * (var_y ** 0.5)), 4)


def _ranks(values: List[float]) -> List[float]:
    """Average (fractional) ranks, ties split evenly -- standard Spearman treatment."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman_rank_correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    return _pearson_correlation(_ranks(xs), _ranks(ys))


def _hit_rate(predicted_by_id: Dict[str, float], actual_by_id: Dict[str, float], n: int) -> Optional[float]:
    ids = list(predicted_by_id)
    if len(ids) < n:
        return None
    predicted_top = {pid for pid in sorted(ids, key=lambda i: -predicted_by_id[i])[:n]}
    actual_top = {pid for pid in sorted(ids, key=lambda i: -actual_by_id[i])[:n]}
    return round(len(predicted_top & actual_top) / n, 3)


@dataclass
class ProjectionSourceMetrics:
    """MAE/RMSE/correlation/rank-correlation/top-N hit rate for ONE
    projection source against actual results. `n` is the number of
    players present in BOTH the predicted and actual maps -- players
    missing from either side are never invented, just excluded, and
    reported via `n`."""

    source: str
    n: int
    mae: Optional[float]
    rmse: Optional[float]
    correlation: Optional[float]
    rank_correlation: Optional[float]
    top5_hit_rate: Optional[float]
    top10_hit_rate: Optional[float]
    top20_hit_rate: Optional[float] = None
    # BlueCollar Live Projection Integration: mean(actual - predicted) --
    # positive means the source under-projects on average, negative means
    # it over-projects. Explicitly requested alongside MAE/RMSE/Pearson/
    # Spearman for the BlueCollar-vs-Big-Money forward evaluation.
    bias: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_projection_source(source: str, predicted_by_id: Dict[str, float], actual_by_id: Dict[str, float]) -> ProjectionSourceMetrics:
    """`predicted_by_id` / `actual_by_id`: {player_id: value}. Only ids
    present in BOTH are evaluated. Returns an all-None metrics record
    (n=0) when there's no overlap, rather than raising -- expected until
    a caller actually has both sides of data for the same slate."""
    shared_ids = [pid for pid in predicted_by_id if pid in actual_by_id]
    if not shared_ids:
        return ProjectionSourceMetrics(source=source, n=0, mae=None, rmse=None, correlation=None, rank_correlation=None, top5_hit_rate=None, top10_hit_rate=None, top20_hit_rate=None)

    predicted = [predicted_by_id[pid] for pid in shared_ids]
    actual = [actual_by_id[pid] for pid in shared_ids]
    errors = [a - p for p, a in zip(predicted, actual)]
    abs_errors = [abs(e) for e in errors]
    n = len(shared_ids)
    predicted_map = {pid: predicted_by_id[pid] for pid in shared_ids}
    actual_map = {pid: actual_by_id[pid] for pid in shared_ids}

    return ProjectionSourceMetrics(
        source=source,
        n=n,
        mae=_mean(abs_errors),
        rmse=round((sum(e * e for e in errors) / n) ** 0.5, 3),
        correlation=_pearson_correlation(predicted, actual),
        rank_correlation=_spearman_rank_correlation(predicted, actual),
        top5_hit_rate=_hit_rate(predicted_map, actual_map, 5),
        top10_hit_rate=_hit_rate(predicted_map, actual_map, 10),
        top20_hit_rate=_hit_rate(predicted_map, actual_map, 20),
        bias=_mean(errors),
    )


def compare_projection_sources(sources: Dict[str, Dict[str, float]], actual_by_id: Dict[str, float]) -> List[ProjectionSourceMetrics]:
    """`sources`: {"external_baseline": {...}, "independent": {...}, "adjusted": {...}}
    (any subset/labeling is fine -- callers decide what they have)."""
    return [evaluate_projection_source(name, preds, actual_by_id) for name, preds in sources.items()]
