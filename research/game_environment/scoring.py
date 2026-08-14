"""Environment scoring for the Game Environment Engine (Milestone DS2).

Produces the four NEW metrics the milestone asks for -- Overall/
Pitcher/Hitter/Stack Environment Score, 0-100 -- from whichever of
weather/vegas/park/bullpen signals are actually available, renormalizing
weights over the available subset (same discipline as
config/scoring_config.py's COMPONENT_WEIGHTS). This module NEVER reads
or writes anything from models/pitcher.py, models/batter.py,
ownership/, optimizer/, or external_projections/ -- it is a fully
independent, additive signal, not a replacement for or input into any
existing projection yet (see FutureAdjustmentPreview in models.py for
the deliberately-disabled placeholder of what that integration would
look like).
"""

from typing import Dict, List, Optional, Tuple

from config.game_environment_config import (
    HITTER_SCORE_WEIGHTS,
    STACK_SCORE_WEIGHTS,
    TOTAL_HIGH_THRESHOLD,
    TOTAL_LOW_THRESHOLD,
)
from research.game_environment.models import (
    BallparkProfile,
    BullpenProfile,
    EnvironmentScore,
    VegasSnapshot,
    WeatherAnalysis,
)

_PARK_FACTOR_LOW = 85
_PARK_FACTOR_HIGH = 115


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _park_component(park: Optional[BallparkProfile]) -> Optional[float]:
    if park is None:
        return None
    return _clamp((park.park_factor - _PARK_FACTOR_LOW) / (_PARK_FACTOR_HIGH - _PARK_FACTOR_LOW) * 100.0)


def _weather_component(weather_analysis: Optional[WeatherAnalysis]) -> Optional[float]:
    if weather_analysis is None:
        return None
    score = 50.0
    for c in weather_analysis.conclusions:
        if c.favors == "hitter":
            score += 15.0
        elif c.favors == "pitcher":
            score -= 15.0
        elif c.favors == "risk":
            score -= 5.0
    return _clamp(score)


def _vegas_component(vegas: Optional[VegasSnapshot]) -> Optional[float]:
    if vegas is None or vegas.current_home.total is None:
        return None
    total = vegas.current_home.total
    return _clamp((total - TOTAL_LOW_THRESHOLD) / (TOTAL_HIGH_THRESHOLD - TOTAL_LOW_THRESHOLD) * 100.0)


def _bullpen_weakness_component(bullpen_home: Optional[BullpenProfile], bullpen_away: Optional[BullpenProfile]) -> Optional[float]:
    """Higher = weaker bullpens on the slate = better for hitters. Uses
    whichever side(s) are available and averages them."""
    strengths: List[float] = []
    for bp in (bullpen_home, bullpen_away):
        if bp is not None and bp.strength_score is not None:
            strengths.append(bp.strength_score)
    if not strengths:
        return None
    avg_strength = sum(strengths) / len(strengths)
    return _clamp(100.0 - avg_strength)


def _weighted_blend(components: Dict[str, Optional[float]], weights: Dict[str, float]) -> float:
    """Renormalizes `weights` over whichever `components` are non-None;
    returns 50.0 (fully neutral) if nothing is available."""
    available: List[Tuple[float, float]] = [(components[k], weights[k]) for k in weights if components.get(k) is not None]
    if not available:
        return 50.0
    total_weight = sum(w for _, w in available)
    return round(sum(v * w for v, w in available) / total_weight, 1)


def score_environment(
    park: Optional[BallparkProfile],
    weather_analysis: Optional[WeatherAnalysis],
    vegas: Optional[VegasSnapshot],
    bullpen_home: Optional[BullpenProfile],
    bullpen_away: Optional[BullpenProfile],
) -> EnvironmentScore:
    """Hitter/Stack scores blend park + weather + vegas total + bullpen
    weakness (higher = better for hitters). Pitcher Score is the
    deterministic complement (100 - Hitter Score) -- an environment
    favorable to hitters is, by construction, unfavorable to pitchers.
    Overall Score uses the same inputs as Hitter Score: in DFS terms,
    "how good is this game's scoring environment" and "how favorable is
    it for hitters" are the same question."""
    components = {
        "park_factor": _park_component(park),
        "weather": _weather_component(weather_analysis),
        "vegas_total": _vegas_component(vegas),
        "bullpen_weakness": _bullpen_weakness_component(bullpen_home, bullpen_away),
    }

    hitter = _weighted_blend(components, HITTER_SCORE_WEIGHTS)
    stack = _weighted_blend(components, STACK_SCORE_WEIGHTS)
    pitcher = round(100.0 - hitter, 1)
    overall = hitter

    return EnvironmentScore(overall=overall, pitcher=pitcher, hitter=hitter, stack=stack)
