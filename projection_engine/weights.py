"""Applies config/projection_engine_config.py's weights to the raw
signals signals.py computed, and blends AI Confidence / AI Risk from
already-computed upstream confidence/risk fields. Every weight and
threshold lives in the config module -- nothing here is a magic number.
"""

import math
from typing import List, Optional, Tuple

from config.projection_engine_config import (
    AI_CONFIDENCE_WEIGHTS,
    EXTERNAL_GAP_MAX_POINTS,
    MAX_TOTAL_ADJUSTMENT_PERCENT,
    PITCHER_ENVIRONMENT_DAMPENING,
    RISK_LARGE_ADJUSTMENT_BUMP_POINTS,
    RISK_LARGE_ADJUSTMENT_THRESHOLD_PERCENT,
    RISK_WEATHER_BUMP_POINTS,
    SIGNAL_WEIGHTS,
    WEATHER_RISK_CODES,
)
from projection_engine.models import RawSignal, SignalContribution

# Categories whose raw delta is already computed from a signal the
# Pitcher Agent partially incorporates for pitchers (via
# GameContext.weather_pitching_factor/park_factor) but not for hitters
# (batter_agent.py hardcodes environment_score=50.0) -- dampened for
# pitchers only, to avoid double-counting.
_PITCHER_DAMPENED_CATEGORIES = {"weather", "park"}


def apply_weight(raw: RawSignal, player_type: str) -> SignalContribution:
    """Turns one RawSignal into a weight-applied SignalContribution."""
    weight = SIGNAL_WEIGHTS.get(raw.category, 0.0)
    delta = raw.raw_delta * weight
    if player_type == "pitcher" and raw.category in _PITCHER_DAMPENED_CATEGORIES:
        delta *= PITCHER_ENVIRONMENT_DAMPENING
        weight *= PITCHER_ENVIRONMENT_DAMPENING
    if raw.category == "external":
        delta = max(-EXTERNAL_GAP_MAX_POINTS, min(EXTERNAL_GAP_MAX_POINTS, delta))
    return SignalContribution(
        category=raw.category,
        label=raw.label,
        raw_delta=raw.raw_delta,
        weight=round(weight, 3),
        delta=round(delta, 3),
        reason=raw.reason,
    )


def cap_total_adjustment(total_delta: float, baseline_projection: Optional[float]) -> Tuple[float, bool]:
    """Caps the summed, weight-applied signal deltas at
    MAX_TOTAL_ADJUSTMENT_PERCENT of the Independent Projection baseline
    -- same defensive discipline as
    config/adjustment_config.py's MAX_POSITIVE/NEGATIVE_ADJUSTMENT_PERCENT.
    A missing/zero baseline means the cap can't be expressed as a
    percentage, so the raw total passes through uncapped."""
    if not baseline_projection or baseline_projection <= 0:
        return total_delta, False
    cap = abs(baseline_projection) * (MAX_TOTAL_ADJUSTMENT_PERCENT / 100.0)
    if total_delta > cap:
        return cap, True
    if total_delta < -cap:
        return -cap, True
    return total_delta, False


def blend_confidence(research_confidence: Optional[float], ownership_confidence: Optional[float], adjustment_confidence: Optional[float]) -> Optional[float]:
    """Weighted blend of already-computed confidence values, renormalized
    over whichever inputs are actually present -- a missing input is
    never treated as 0. Returns None only if every input is missing."""
    inputs = {
        "research": research_confidence,
        "ownership": ownership_confidence,
        "adjustment": adjustment_confidence,
    }
    available = {k: v for k, v in inputs.items() if v is not None}
    if not available:
        return None
    weight_sum = sum(AI_CONFIDENCE_WEIGHTS[k] for k in available)
    if weight_sum <= 0:
        return None
    blended = sum(available[k] * AI_CONFIDENCE_WEIGHTS[k] for k in available) / weight_sum
    return round(max(0.0, min(100.0, blended)), 1)


def blend_risk(base_risk: Optional[float], signals: List[SignalContribution], weather_analysis: Optional[dict], total_adjustment_percent: Optional[float]) -> Optional[float]:
    """Starts from the Agent's own risk_score and adds small bumps for
    conditions the AI layer newly observes: a weather risk conclusion
    (rain/postponement) present on the game, or a large total adjustment
    magnitude implying the signals meaningfully disagreed with the
    independent baseline."""
    if base_risk is None:
        return None
    risk = base_risk

    if weather_analysis:
        for conclusion in weather_analysis.get("conclusions", []):
            if conclusion.get("code") in WEATHER_RISK_CODES:
                risk += RISK_WEATHER_BUMP_POINTS

    if total_adjustment_percent is not None and abs(total_adjustment_percent) >= RISK_LARGE_ADJUSTMENT_THRESHOLD_PERCENT:
        risk += RISK_LARGE_ADJUSTMENT_BUMP_POINTS

    return round(max(0.0, min(100.0, risk)), 1)


def is_finite_number(value) -> bool:
    """True for a real, finite int/float -- False for None, NaN, +/-inf,
    or a non-numeric type. Shared by validator.py."""
    if value is None or isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return not (math.isnan(value) or math.isinf(value))
