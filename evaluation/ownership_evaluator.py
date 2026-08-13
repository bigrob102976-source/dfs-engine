"""Grades Ownership Model V1 (projected_ownership) against actual
(post-lock) DraftKings contest ownership. Pure computation -- no network,
no file I/O (callers load the ownership snapshot and actual-ownership
document JSON and hand them in as plain dicts/lists).

Mirrors evaluation/pitcher_evaluator.py's structure and reuses its two
pure numeric helpers (_mean, _pearson_correlation) rather than
duplicating them. Never writes back into either the ownership snapshot
(immutable) or the actual-ownership import (also immutable), and never
touches ownership/model.py or its config -- this milestone is
measurement, not tuning (see config/ownership_evaluation_config.py).

Ranks are computed WITHIN player_type (pitchers ranked among matched
pitchers, hitters among matched hitters) since projected_ownership
itself is normalized separately by type.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config import ownership_evaluation_config as eval_cfg
from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS
from config.ownership_config import OWNERSHIP_TIER_THRESHOLDS
from evaluation.pitcher_evaluator import _mean, _pearson_correlation
from ownership.slate_normalization import compute_ranks

# ----------------------------------------------------------------------------
# Small helpers specific to ownership evaluation
# ----------------------------------------------------------------------------


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return round(s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2, 3)


def _ownership_tier(value: float) -> str:
    for name, lo, hi in OWNERSHIP_TIER_THRESHOLDS:
        if lo <= value < hi:
            return name
    return OWNERSHIP_TIER_THRESHOLDS[-1][0]


# ----------------------------------------------------------------------------
# Join projected (snapshot) vs actual (imported) ownership
# ----------------------------------------------------------------------------


def _build_records(snapshot_players: List[dict], actual_records: List[dict]) -> List[dict]:
    actual_by_dk_id = {
        r["dk_player_id"]: r for r in actual_records if r.get("match_status") == "matched" and r.get("dk_player_id")
    }

    records = []
    for p in snapshot_players:
        actual = actual_by_dk_id.get(p["dk_player_id"])
        matched = actual is not None
        projected = p.get("projected_ownership")
        actual_own = actual["actual_ownership"] if actual else None

        error = abs_error = squared_error = None
        chalk_correct = None
        if matched and projected is not None and actual_own is not None:
            error = round(actual_own - projected, 3)
            abs_error = round(abs(error), 3)
            squared_error = round(error * error, 4)
            predicted_chalk = projected >= eval_cfg.CHALK_EVAL_OWNERSHIP_THRESHOLD
            actual_chalk = actual_own >= eval_cfg.CHALK_EVAL_OWNERSHIP_THRESHOLD
            chalk_correct = predicted_chalk == actual_chalk

        records.append({
            "dk_player_id": p["dk_player_id"],
            "mlb_player_id": p.get("mlb_player_id"),
            "name": p["name"],
            "team": p.get("team"),
            "player_type": p.get("player_type"),
            "salary": p.get("salary"),
            "dk_positions": p.get("dk_positions") or [],
            "tags": p.get("tags") or [],
            "matched": matched,
            "projected_ownership": projected,
            "actual_ownership": actual_own,
            "error": error,
            "abs_error": abs_error,
            "squared_error": squared_error,
            "projected_rank": None,
            "actual_rank": None,
            "rank_error": None,
            "ownership_tier_projected": p.get("ownership_tier"),
            "ownership_tier_actual": _ownership_tier(actual_own) if actual_own is not None else None,
            "chalk_correct": chalk_correct,
            "leverage_score": p.get("leverage_score"),
            "chalk_score": p.get("chalk_score"),
        })
    return records


def _assign_ranks(records: List[dict]) -> None:
    for player_type in ("pitcher", "hitter"):
        group = [r for r in records if r["matched"] and r["player_type"] == player_type]
        by_proj = sorted(group, key=lambda r: -r["projected_ownership"])
        by_actual = sorted(group, key=lambda r: -r["actual_ownership"])
        proj_rank = {r["dk_player_id"]: i + 1 for i, r in enumerate(by_proj)}
        actual_rank = {r["dk_player_id"]: i + 1 for i, r in enumerate(by_actual)}
        for r in group:
            r["projected_rank"] = proj_rank[r["dk_player_id"]]
            r["actual_rank"] = actual_rank[r["dk_player_id"]]
            r["rank_error"] = r["actual_rank"] - r["projected_rank"]


# ----------------------------------------------------------------------------
# Slate-level metrics (reused for overall / pitchers / hitters)
# ----------------------------------------------------------------------------


def _slate_metrics(group: List[dict]) -> dict:
    n = len(group)
    if n == 0:
        return {
            "count": 0, "mae": None, "rmse": None, "correlation": None, "rank_correlation": None,
            "bias": None, "median_abs_error": None, "max_abs_error": None,
        }
    abs_errors = [r["abs_error"] for r in group]
    errors = [r["error"] for r in group]
    squared_errors = [r["squared_error"] for r in group]
    have_ranks = all(r["projected_rank"] is not None and r["actual_rank"] is not None for r in group)
    return {
        "count": n,
        "mae": _mean(abs_errors),
        "rmse": round((sum(squared_errors) / n) ** 0.5, 3),
        "correlation": _pearson_correlation([r["projected_ownership"] for r in group], [r["actual_ownership"] for r in group]),
        "rank_correlation": (
            _pearson_correlation([r["projected_rank"] for r in group], [r["actual_rank"] for r in group])
            if have_ranks else None
        ),
        "bias": _mean(errors),
        "median_abs_error": _median(abs_errors),
        "max_abs_error": round(max(abs_errors), 3),
    }


# ----------------------------------------------------------------------------
# Tier evaluation
# ----------------------------------------------------------------------------


def _tier_summary(matched: List[dict]) -> List[dict]:
    summary = []
    for tier_name, _lo, _hi in OWNERSHIP_TIER_THRESHOLDS:
        group = [r for r in matched if r["ownership_tier_projected"] == tier_name]
        summary.append({
            "tier": tier_name, "count": len(group),
            "avg_projected_ownership": _mean([r["projected_ownership"] for r in group]),
            "avg_actual_ownership": _mean([r["actual_ownership"] for r in group]),
            "mae": _mean([r["abs_error"] for r in group]),
            "avg_error": _mean([r["error"] for r in group]),
        })
    return summary


def _tier_confusion(matched: List[dict]) -> Dict[str, Dict[str, int]]:
    tier_names = [t[0] for t in OWNERSHIP_TIER_THRESHOLDS]
    confusion = {p: {a: 0 for a in tier_names} for p in tier_names}
    for r in matched:
        pt, at = r["ownership_tier_projected"], r["ownership_tier_actual"]
        if pt in confusion and at in confusion.get(pt, {}):
            confusion[pt][at] += 1
    return confusion


# ----------------------------------------------------------------------------
# Chalk evaluation
# ----------------------------------------------------------------------------


def _chalk_sets(matched: List[dict]) -> Tuple[set, set]:
    if eval_cfg.CHALK_EVAL_MODE == "top_n":
        n = eval_cfg.CHALK_EVAL_TOP_N
        predicted = {r["dk_player_id"] for r in sorted(matched, key=lambda r: -r["projected_ownership"])[:n]}
        actual = {r["dk_player_id"] for r in sorted(matched, key=lambda r: -r["actual_ownership"])[:n]}
    else:
        t = eval_cfg.CHALK_EVAL_OWNERSHIP_THRESHOLD
        predicted = {r["dk_player_id"] for r in matched if r["projected_ownership"] >= t}
        actual = {r["dk_player_id"] for r in matched if r["actual_ownership"] >= t}
    return predicted, actual


def _chalk_precision_recall(matched: List[dict]) -> dict:
    predicted, actual = _chalk_sets(matched)
    precision = round(len(predicted & actual) / len(predicted), 3) if predicted else None
    recall = round(len(predicted & actual) / len(actual), 3) if actual else None
    return {
        "mode": eval_cfg.CHALK_EVAL_MODE, "predicted_chalk_count": len(predicted), "actual_chalk_count": len(actual),
        "precision": precision, "recall": recall,
    }


def _hit_rate(matched: List[dict], n: int) -> Optional[float]:
    if len(matched) < n:
        return None
    predicted_top = {r["dk_player_id"] for r in sorted(matched, key=lambda r: -r["projected_ownership"])[:n]}
    actual_top = {r["dk_player_id"] for r in sorted(matched, key=lambda r: -r["actual_ownership"])[:n]}
    return round(len(predicted_top & actual_top) / n, 3)


# ----------------------------------------------------------------------------
# Biggest misses
# ----------------------------------------------------------------------------


def _biggest_misses(matched: List[dict], n: int) -> Tuple[List[dict], List[dict]]:
    scored = [r for r in matched if r["error"] is not None]
    under_projected = sorted(scored, key=lambda r: -r["error"])[:n]  # actual > projected
    over_projected = sorted(scored, key=lambda r: r["error"])[:n]    # projected > actual
    return under_projected, over_projected


# ----------------------------------------------------------------------------
# Tag / position / salary-band / team breakdowns
# ----------------------------------------------------------------------------


def _tag_performance(matched: List[dict]) -> List[dict]:
    performance = []
    for tag in eval_cfg.TAGS_TO_EVALUATE:
        group = [r for r in matched if tag in r["tags"]]
        performance.append({
            "tag": tag, "count": len(group),
            "avg_projected_ownership": _mean([r["projected_ownership"] for r in group]),
            "avg_actual_ownership": _mean([r["actual_ownership"] for r in group]),
            "avg_error": _mean([r["error"] for r in group]),
        })
    return performance


def _position_evaluation(matched_hitters: List[dict]) -> List[dict]:
    """Multi-position hitters are counted in EVERY DK-eligible position
    group (documented, not silently double-counted -- overall/combined
    metrics are computed once per player regardless)."""
    positions = [s["slot"] for s in DK_CLASSIC_ROSTER_SLOTS if s["slot"] != "P"]
    summary = []
    for pos in positions:
        group = [r for r in matched_hitters if pos in r["dk_positions"]]
        summary.append({
            "position": pos, "count": len(group),
            "mae": _mean([r["abs_error"] for r in group]), "avg_error": _mean([r["error"] for r in group]),
        })
    return summary


def _salary_band_evaluation(matched: List[dict], bands: List[tuple]) -> List[dict]:
    summary = []
    for lo, hi, label in bands:
        group = [r for r in matched if r["salary"] is not None and lo <= r["salary"] < hi]
        summary.append({
            "band": label, "count": len(group), "mae": _mean([r["abs_error"] for r in group]),
            "bias": _mean([r["error"] for r in group]), "avg_actual_ownership": _mean([r["actual_ownership"] for r in group]),
        })
    return summary


def _team_popularity_evaluation(matched_hitters: List[dict], snapshot_team_popularity: dict) -> List[dict]:
    """Aggregate PLAYER ownership by team -- explicitly NOT a lineup-
    level stack-combination probability (see the milestone's warning)."""
    actual_agg: Dict[str, float] = {}
    for r in matched_hitters:
        if r["team"]:
            actual_agg[r["team"]] = actual_agg.get(r["team"], 0.0) + (r["actual_ownership"] or 0.0)
    projected_agg = {team: stats.get("aggregate_projected_ownership", 0.0) for team, stats in snapshot_team_popularity.items()}

    teams = sorted(set(actual_agg) | set(projected_agg))
    actual_full = {t: round(actual_agg.get(t, 0.0), 2) for t in teams}
    projected_full = {t: round(projected_agg.get(t, 0.0), 2) for t in teams}
    actual_ranks = compute_ranks(list(actual_full.items()), descending=True)
    projected_ranks = compute_ranks(list(projected_full.items()), descending=True)

    rows = []
    for team in teams:
        pr, ar = projected_ranks.get(team), actual_ranks.get(team)
        rows.append({
            "team": team,
            "projected_aggregate_player_ownership": projected_full[team],
            "actual_aggregate_player_ownership": actual_full[team],
            "projected_rank": pr, "actual_rank": ar,
            "rank_error": (ar - pr) if pr is not None and ar is not None else None,
        })
    rows.sort(key=lambda r: r["actual_rank"] if r["actual_rank"] is not None else 999)
    return rows


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


@dataclass
class OwnershipEvaluationReport:
    slate_date: str
    ownership_model_version: str
    evaluator_version: str
    generated_at: str

    ownership_snapshot_path: Optional[str]
    ownership_snapshot_generated_at: str
    actual_ownership_source_file: Optional[str]

    contest_id: Optional[str]
    contest_name: Optional[str]
    contest_size: Optional[int]

    snapshot_player_count: int
    actual_record_count: int
    matched_count: int
    unmatched_count: int
    ambiguous_count: int
    match_rate: float

    overall_metrics: dict
    pitcher_metrics: dict
    hitter_metrics: dict

    tier_summary: List[dict]
    tier_confusion: Dict[str, Dict[str, int]]

    chalk_evaluation: dict
    top5_hit_rate: Optional[float]
    top10_hit_rate: Optional[float]

    top_actual_ownership: List[dict]
    biggest_under_projections: List[dict]
    biggest_over_projections: List[dict]

    tag_performance: List[dict]
    position_evaluation: List[dict]
    pitcher_salary_band_evaluation: List[dict]
    hitter_salary_band_evaluation: List[dict]
    team_popularity_evaluation: List[dict]

    records: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_ownership(
    ownership_snapshot: dict, actual_ownership_document: dict,
    ownership_snapshot_path: Optional[str] = None,
) -> OwnershipEvaluationReport:
    snapshot_players = ownership_snapshot["players"]
    actual_records = actual_ownership_document["records"]
    contest = actual_ownership_document.get("contest", {})

    records = _build_records(snapshot_players, actual_records)
    _assign_ranks(records)
    matched = [r for r in records if r["matched"]]
    matched_hitters = [r for r in matched if r["player_type"] == "hitter"]
    matched_pitchers = [r for r in matched if r["player_type"] == "pitcher"]

    return OwnershipEvaluationReport(
        slate_date=ownership_snapshot["slate_date"],
        ownership_model_version=ownership_snapshot.get("model_version", "unknown"),
        evaluator_version=eval_cfg.OWNERSHIP_EVALUATOR_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(),
        ownership_snapshot_path=ownership_snapshot_path,
        ownership_snapshot_generated_at=ownership_snapshot.get("generated_at", ""),
        actual_ownership_source_file=contest.get("results_filename"),
        contest_id=contest.get("contest_id"),
        contest_name=contest.get("contest_name"),
        contest_size=contest.get("entries"),
        snapshot_player_count=len(snapshot_players),
        actual_record_count=len(actual_records),
        matched_count=len(matched),
        unmatched_count=sum(1 for r in actual_records if r.get("match_status") == "unmatched"),
        ambiguous_count=sum(1 for r in actual_records if r.get("match_status") == "ambiguous"),
        match_rate=round(len(matched) / len(actual_records), 4) if actual_records else 0.0,
        overall_metrics=_slate_metrics(matched),
        pitcher_metrics=_slate_metrics(matched_pitchers),
        hitter_metrics=_slate_metrics(matched_hitters),
        tier_summary=_tier_summary(matched),
        tier_confusion=_tier_confusion(matched),
        chalk_evaluation=_chalk_precision_recall(matched),
        top5_hit_rate=_hit_rate(matched, 5),
        top10_hit_rate=_hit_rate(matched, 10),
        top_actual_ownership=sorted(matched, key=lambda r: -r["actual_ownership"])[:eval_cfg.TOP_ACTUAL_OWNERSHIP_DISPLAY_COUNT],
        biggest_under_projections=_biggest_misses(matched, eval_cfg.BIGGEST_MISSES_COUNT)[0],
        biggest_over_projections=_biggest_misses(matched, eval_cfg.BIGGEST_MISSES_COUNT)[1],
        tag_performance=_tag_performance(matched),
        position_evaluation=_position_evaluation(matched_hitters),
        pitcher_salary_band_evaluation=_salary_band_evaluation(matched_pitchers, eval_cfg.PITCHER_SALARY_BANDS),
        hitter_salary_band_evaluation=_salary_band_evaluation(matched_hitters, eval_cfg.HITTER_SALARY_BANDS),
        team_popularity_evaluation=_team_popularity_evaluation(matched_hitters, ownership_snapshot.get("team_popularity", {})),
        records=records,
    )
