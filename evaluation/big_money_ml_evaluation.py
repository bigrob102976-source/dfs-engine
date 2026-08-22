"""Milestone 32.2B -- Big Money ML forward (2026+) evaluation.

Compares Big Money ML against Native/AI/FantasyPros/Independent/Actual
DK, using ONLY genuinely pregame-captured ML projections
(LIVE_PREGAME/PREGAME_FROZEN status -- both were captured before that
game's first pitch). MISSING/INVALID_FEATURE_PARITY rows are always
excluded, never backfilled retroactively.

This module is POSTGAME evaluation tooling (reads results/, same as
every other evaluator in this package) -- it is allowed to import
big_money_ml's read-only persistence loader, the reverse direction
(big_money_ml importing evaluation) remains forbidden, see
tests/test_architecture_separation.py.

Never retrains, never tunes any model based on what this module finds
-- 2026+ results are evaluation data only.
"""

from typing import Dict, List, Optional

from evaluation.projection_source_comparison import ProjectionSourceMetrics, compare_projection_sources
from evaluation.projection_source_loader import DEFAULT_RESULTS_ROOT, build_pitcher_projection_sources, load_actual_pitcher_points
from fantasypros.persistence import DEFAULT_SNAPSHOT_ROOT as DEFAULT_FANTASYPROS_ROOT
from fantasypros.persistence import load_latest_snapshot as load_latest_fantasypros_snapshot

from big_money_ml.persistence import DEFAULT_ML_PROJECTION_ROOT, load_latest_ml_projection_snapshot

_VALID_PREGAME_STATUSES = {"LIVE_PREGAME", "PREGAME_FROZEN"}


def load_pregame_ml_pitcher_projections(slate_date: str, ml_root=DEFAULT_ML_PROJECTION_ROOT) -> Dict[str, float]:
    """{player_id: projection} for pitchers whose ML projection was
    GENUINELY captured before their game started. A MISSING or
    INVALID_FEATURE_PARITY row is never included here, and a game that
    started with no valid pregame snapshot is never backfilled."""
    doc = load_latest_ml_projection_snapshot(slate_date, output_root=ml_root)
    if not doc:
        return {}
    return {
        str(p["player_id"]): p["projection"]
        for p in doc.get("players", [])
        if p.get("projection_status") in _VALID_PREGAME_STATUSES and p.get("projection") is not None
    }


def load_fantasypros_pitcher_projections(slate_date: str, fp_root=DEFAULT_FANTASYPROS_ROOT) -> Dict[str, float]:
    """{player_id: dk_points} for pitchers FantasyPros' own identity
    resolver actually matched to an mlb_player_id -- an unmatched
    FantasyPros row is never guessed into the comparison by name."""
    snapshot = load_latest_fantasypros_snapshot(slate_date, output_root=fp_root)
    if not snapshot:
        return {}
    return {
        str(p["mlb_player_id"]): p["dk_points"]
        for p in snapshot.get("players", [])
        if p.get("player_type") == "pitcher" and p.get("mlb_player_id") and p.get("dk_points") is not None
    }


def build_all_pitcher_projection_sources(
    slate_date: str, ml_root=DEFAULT_ML_PROJECTION_ROOT, fantasypros_root=DEFAULT_FANTASYPROS_ROOT, **other_source_roots,
) -> Dict[str, Dict[str, float]]:
    """{source_label: {player_id: value}} across every source that
    actually has data for this date -- native/ai/independent/external/
    adjusted (via the existing generic loader) plus big_money_ml and
    fantasypros. A source with nothing for this date is simply omitted.
    `other_source_roots` passes through to build_pitcher_projection_sources
    (predictions_root/adjusted_root/ai_root/native_root)."""
    sources = build_pitcher_projection_sources(slate_date, **other_source_roots)

    ml = load_pregame_ml_pitcher_projections(slate_date, ml_root=ml_root)
    if ml:
        sources["big_money_ml"] = ml

    fantasypros = load_fantasypros_pitcher_projections(slate_date, fp_root=fantasypros_root)
    if fantasypros:
        sources["fantasypros"] = fantasypros

    return sources


def _weighted_mean(values: List[Optional[float]], weights: List[int]) -> Optional[float]:
    pairs = [(v, w) for v, w in zip(values, weights) if v is not None and w > 0]
    if not pairs:
        return None
    total_weight = sum(w for _, w in pairs)
    return round(sum(v * w for v, w in pairs) / total_weight, 3)


def _simple_mean(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 3) if clean else None


def evaluate_forward_performance(slate_dates: List[str], results_root=DEFAULT_RESULTS_ROOT, ml_root=DEFAULT_ML_PROJECTION_ROOT) -> dict:
    """Per-source forward comparison, pooled across `slate_dates`. Only
    dates with actual results already collected are included -- a date
    with no results yet contributes nothing (never invented). Every
    source's MAE/RMSE are the sample-size-weighted mean across the dates
    it actually appeared on; top-5/top-10 hit rates are the simple mean
    of that per-date metric (a slate-level DFS concept, not something
    that can be pooled across dates as one flat rank). SHARED SAMPLE N
    is reported per source (the count of player-date pairs where that
    source AND actual results were both present) -- documented
    simplification: each source is compared against the pitchers IT
    covers, not a further intersection across every other source too."""
    per_source_metrics: Dict[str, List[ProjectionSourceMetrics]] = {}
    dates_evaluated = 0
    dates_with_ml_pregame_data = 0

    for date in slate_dates:
        actual = load_actual_pitcher_points(date, results_root=results_root)
        if not actual:
            continue  # no results collected yet for this date -- skip, never invent
        dates_evaluated += 1

        sources = build_all_pitcher_projection_sources(date, ml_root=ml_root)
        if "big_money_ml" in sources:
            dates_with_ml_pregame_data += 1

        for metrics in compare_projection_sources(sources, actual):
            per_source_metrics.setdefault(metrics.source, []).append(metrics)

    source_results = []
    for source, metric_list in sorted(per_source_metrics.items()):
        valid = [m for m in metric_list if m.n > 0]
        if not valid:
            continue
        source_results.append({
            "source": source,
            "shared_sample_n": sum(m.n for m in valid),
            "dates_included": len(valid),
            "mae": _weighted_mean([m.mae for m in valid], [m.n for m in valid]),
            "rmse": _weighted_mean([m.rmse for m in valid], [m.n for m in valid]),
            "pearson": _weighted_mean([m.correlation for m in valid], [m.n for m in valid]),
            "spearman": _weighted_mean([m.rank_correlation for m in valid], [m.n for m in valid]),
            "avg_top5_hit_rate": _simple_mean([m.top5_hit_rate for m in valid]),
            "avg_top10_hit_rate": _simple_mean([m.top10_hit_rate for m in valid]),
        })

    return {
        "slates_requested": len(slate_dates),
        "slates_with_actual_results": dates_evaluated,
        "slates_with_ml_pregame_data": dates_with_ml_pregame_data,
        "source_metrics": source_results,
    }


def compute_disaster_start_bucket(
    slate_dates: List[str], threshold: float = 2.0, results_root=DEFAULT_RESULTS_ROOT, ml_root=DEFAULT_ML_PROJECTION_ROOT,
) -> dict:
    """Milestone 32.2 identified mild under-projection of blow-up/
    disaster starts on the historical TEST set. This tracks whether that
    pattern persists on genuinely FORWARD (2026+) results -- an
    evaluation bucket only, never used to alter the model in this
    milestone (see M32.2B's explicit 'do NOT tune based on this'
    instruction)."""
    predicted: List[float] = []
    actual: List[float] = []
    dates_included = 0

    for date in slate_dates:
        ml = load_pregame_ml_pitcher_projections(date, ml_root=ml_root)
        actual_by_id = load_actual_pitcher_points(date, results_root=results_root)
        if not ml or not actual_by_id:
            continue
        found_this_date = False
        for player_id, actual_points in actual_by_id.items():
            if actual_points <= threshold and player_id in ml:
                predicted.append(ml[player_id])
                actual.append(actual_points)
                found_this_date = True
        if found_this_date:
            dates_included += 1

    if not predicted:
        return {"n": 0, "threshold": threshold, "dates_with_disaster_starts": 0, "bias": None, "mae": None}

    errors = [p - a for p, a in zip(predicted, actual)]
    return {
        "n": len(predicted), "threshold": threshold, "dates_with_disaster_starts": dates_included,
        "bias": round(sum(errors) / len(errors), 3),
        "mae": round(sum(abs(e) for e in errors) / len(errors), 3),
    }
