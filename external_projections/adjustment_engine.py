"""The Big Money Research Adjustment Layer (Milestone 17): a
DETERMINISTIC function of already-computed Pitcher/Batter Agent
research (trend_metrics, opposing_pitcher/opponent_stats, confidence)
that nudges an external provider's baseline projection toward what our
own structured research suggests. This is NOT an LLM free-form
projection generator -- every signal, threshold, and point delta is
defined in config/adjustment_config.py, and total movement is always
capped (see apply_adjustment).
"""

import dataclasses
from typing import Dict, List, Optional

from config.adjustment_config import (
    BATTER_SIGNALS,
    BIG_MONEY_ADJUSTMENT_VERSION,
    CONFIDENCE_ADJUSTMENT_CAPS,
    DEFAULT_CONFIDENCE_ADJUSTMENT_CAP_PERCENT,
    MAX_NEGATIVE_ADJUSTMENT_PERCENT,
    MAX_POSITIVE_ADJUSTMENT_PERCENT,
    PITCHER_SIGNALS,
)
from external_projections.models import AdjustmentFactor, PlayerProjectionRecord, ProjectionMergeResult

_SIGNALS_BY_PLAYER_TYPE = {"pitcher": PITCHER_SIGNALS, "hitter": BATTER_SIGNALS}


def _get_nested(record: dict, path) -> Optional[float]:
    value = record
    for key in path:
        if value is None:
            return None
        value = value.get(key)
    return value if isinstance(value, (int, float)) else None


def compute_signals(player_type: str, research_record: dict) -> List[AdjustmentFactor]:
    """`player_type` is "pitcher" | "hitter". `research_record` is a raw
    pitcher_board/batter_board snapshot record (has trend_metrics,
    opponent_stats/opposing_pitcher, confidence). Only signals whose
    underlying field is actually present fire -- a missing stat is never
    treated as neutral or zero."""
    signal_defs = _SIGNALS_BY_PLAYER_TYPE.get(player_type, [])
    confidence = research_record.get("confidence")
    factors: List[AdjustmentFactor] = []

    for sig in signal_defs:
        value = _get_nested(research_record, sig["path"])
        if value is None:
            continue
        if value > sig["positive_threshold"]:
            factors.append(AdjustmentFactor(factor=sig["factor"], delta=sig["positive_delta"], reason=sig["positive_reason"], confidence=confidence))
        elif value < sig["negative_threshold"]:
            factors.append(AdjustmentFactor(factor=sig["factor"], delta=sig["negative_delta"], reason=sig["negative_reason"], confidence=confidence))

    return factors


def confidence_adjustment_cap(confidence: Optional[float]) -> float:
    """Lower research confidence -> a tighter cap on how far the
    adjustment can move the projection, independent of the absolute
    MAX_POSITIVE/NEGATIVE_ADJUSTMENT_PERCENT caps (both apply -- the
    tighter one wins, see apply_adjustment)."""
    if confidence is None:
        return DEFAULT_CONFIDENCE_ADJUSTMENT_CAP_PERCENT
    for band in CONFIDENCE_ADJUSTMENT_CAPS:
        if confidence >= band["min_confidence"]:
            return band["max_percent"]
    return DEFAULT_CONFIDENCE_ADJUSTMENT_CAP_PERCENT


def apply_adjustment(
    external_projection: Optional[float], external_ceiling: Optional[float], external_floor: Optional[float],
    factors: List[AdjustmentFactor], confidence: Optional[float],
) -> dict:
    """Sums the signal deltas, converts to a percent of the external
    baseline, clamps to min(confidence cap, absolute cap), and applies
    the SAME clamped percent proportionally to ceiling/floor. Returns a
    dict of adjusted_projection/adjusted_ceiling/adjusted_floor/
    adjustment_delta/adjustment_percent/adjustment_confidence/capped."""
    if external_projection is None or external_projection == 0:
        return {
            "adjusted_projection": external_projection, "adjusted_ceiling": external_ceiling, "adjusted_floor": external_floor,
            "adjustment_delta": 0.0, "adjustment_percent": 0.0, "adjustment_confidence": confidence, "capped": False,
        }

    raw_delta = sum(f.delta for f in factors)
    raw_percent = (raw_delta / external_projection) * 100.0

    conf_cap = confidence_adjustment_cap(confidence)
    abs_cap = MAX_POSITIVE_ADJUSTMENT_PERCENT if raw_percent >= 0 else MAX_NEGATIVE_ADJUSTMENT_PERCENT
    effective_cap = min(conf_cap, abs_cap)
    clamped_percent = max(-effective_cap, min(effective_cap, raw_percent))
    capped = abs(clamped_percent - raw_percent) > 1e-9

    adjustment_delta = round(external_projection * clamped_percent / 100.0, 2)
    adjusted_projection = round(external_projection + adjustment_delta, 2)
    adjusted_ceiling = round(external_ceiling * (1 + clamped_percent / 100.0), 2) if external_ceiling is not None else None
    adjusted_floor = round(external_floor * (1 + clamped_percent / 100.0), 2) if external_floor is not None else None

    return {
        "adjusted_projection": adjusted_projection, "adjusted_ceiling": adjusted_ceiling, "adjusted_floor": adjusted_floor,
        "adjustment_delta": adjustment_delta, "adjustment_percent": round(clamped_percent, 2),
        "adjustment_confidence": confidence, "capped": capped,
    }


def build_adjusted_records(merge_result: ProjectionMergeResult, research_records_by_id: Dict[str, dict]) -> List[PlayerProjectionRecord]:
    """Given the output of projection_merge.match_external_to_independent
    and the SAME research records (keyed by our own player_id) used to
    build that merge, computes and attaches adjusted_* fields to a NEW
    list of records -- the merge_result's own records are never mutated.
    A record whose research data or external baseline is missing simply
    keeps adjusted_* as None -- it is never invented."""
    adjusted: List[PlayerProjectionRecord] = []
    for record in merge_result.records:
        research_record = research_records_by_id.get(record.independent_player_id)
        if research_record is None or record.external_projection is None:
            adjusted.append(record)
            continue

        factors = compute_signals(record.player_type, research_record)
        result = apply_adjustment(record.external_projection, record.external_ceiling, record.external_floor, factors, research_record.get("confidence"))

        adjusted.append(dataclasses.replace(
            record,
            adjusted_projection=result["adjusted_projection"], adjusted_ceiling=result["adjusted_ceiling"],
            adjusted_floor=result["adjusted_floor"], adjustment_delta=result["adjustment_delta"],
            adjustment_percent=result["adjustment_percent"], adjustment_confidence=result["adjustment_confidence"],
            adjustment_reasons=[f.reason for f in factors], adjustments=factors,
        ))
    return adjusted


__all__ = [
    "BIG_MONEY_ADJUSTMENT_VERSION",
    "compute_signals",
    "confidence_adjustment_cap",
    "apply_adjustment",
    "build_adjusted_records",
]
