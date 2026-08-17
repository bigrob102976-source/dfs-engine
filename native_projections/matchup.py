"""Matchup Adjustment layer: hitter-vs-opposing-pitcher (platoon-aware),
pitcher-vs-opposing-lineup, and game-environment (park/weather/Vegas/
bullpen) adjustments, all expressed as small, capped DK-POINTS deltas
applied on top of the base projection dk_scoring.py computes from the
regressed event rates (hitter_rates.py / pitcher_rates.py).

This module intentionally reuses the EXISTING, already-approved
normalization bounds from config.batter_scoring_config.RANGES["matchup"]
and config.scoring_config.RANGES["matchup"]/["run_prevention"] rather than
inventing new ones -- those ranges are the same ones agents/batter_agent.py
and agents/pitcher_agent.py already use to turn a raw stat into a 0-100
sub-score, so reusing them here means "favorable matchup" means the same
thing in both the Independent Projection and the Native Projection Model.

--------------------------------------------------------------------------
Double-counting control (the milestone's explicit requirement)
--------------------------------------------------------------------------
Park factor is REAL, static reference data (config/game_environment_config.py
::BALLPARKS) and always gets its full, direct, documented weight
(PARK_HITTER_POINTS_PER_FACTOR_POINT / PARK_PITCHER_POINTS_PER_FACTOR_POINT).

Vegas / Weather / Bullpen are all backed ONLY by mock providers today
(confirmed via audit: MockVegasProvider/MockWeatherProvider/
MockBullpenProvider, research/game_environment/*.py -- is_mock=True on
every snapshot). Each is capped at its own small MOCK_*_MAX_POINTS ceiling
(config.native_projection_config) rather than being applied at full
independent weight -- both because a synthetic signal should never move a
real-money projection as much as a real one, and because Vegas/weather/
bullpen are themselves correlated proxies for the SAME underlying "run
environment" that park factor already partially captures; stacking all
four at full weight would double-count that one real signal four times.
If a real (non-mock) Vegas/weather/bullpen provider is ever configured,
`is_mock=False` on its snapshot automatically raises the cap toward the
`REAL_*` constant -- no code change needed here, only new provider wiring
elsewhere.

--------------------------------------------------------------------------
Opposing lineup quality (new -- fills a genuine gap the audit found)
--------------------------------------------------------------------------
research/opposing_pitcher_context.py already lets a HITTER see his
opposing starter's real underlying metrics. No equivalent existed for a
PITCHER to see his opposing LINEUP's real aggregate quality -- pitchers
only ever saw a team-overall K% (models.pitcher.OpponentStats). This
module's build_opposing_lineup_index() mirrors that existing module's
index-then-attach pattern in reverse: aggregate real per-hitter season
rates (K%/BB%/ISO/wOBA) across the CONFIRMED lineup only.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import native_projection_config as cfg
from config.batter_scoring_config import COMPONENT_WEIGHTS as _BATTER_WEIGHTS
from config.batter_scoring_config import RANGES as _BATTER_RANGES
from config.projection_engine_config import BULLPEN_STRENGTH_ELITE, BULLPEN_STRENGTH_WEAK
from config.scoring_config import COMPONENT_WEIGHTS as _PITCHER_WEIGHTS
from config.scoring_config import RANGES as _PITCHER_RANGES
from models.batter import BatterInput
from models.pitcher import PitcherInput


@dataclass
class AdjustmentResult:
    points: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class OpposingLineupQuality:
    team: str
    hitters_count: int
    avg_k_percent: Optional[float]
    avg_bb_percent: Optional[float]
    avg_iso: Optional[float]
    avg_woba: Optional[float]
    is_partial: bool


def _normalize(value: Optional[float], low: float, high: float, invert: bool) -> Optional[float]:
    """Linearly scale `value` into a 0..1 "favorability" score, clipped at
    the ends. `invert=True` means a LOWER raw value is more favorable --
    same convention as every existing RANGES table in this project."""
    if value is None:
        return None
    if high == low:
        return 0.5
    n = (value - low) / (high - low)
    n = max(0.0, min(1.0, n))
    return 1.0 - n if invert else n


def _weighted_favorability(components: Dict[str, Optional[float]], weights: Dict[str, float]) -> Optional[float]:
    total_weight = 0.0
    total = 0.0
    for key, value in components.items():
        if value is None:
            continue
        w = weights.get(key, 0.0)
        total += value * w
        total_weight += w
    if total_weight <= 0:
        return None
    return total / total_weight


def _points_from_favorability(favorability: Optional[float], cap: float) -> Optional[float]:
    if favorability is None:
        return None
    return (favorability - 0.5) * 2 * cap


# ----------------------------------------------------------------------------
# Hitter vs. opposing pitcher (platoon-aware)
# ----------------------------------------------------------------------------


def hitter_matchup_adjustment(b: BatterInput) -> AdjustmentResult:
    opp = b.opposing_pitcher
    if opp.player_id is None:
        return AdjustmentResult(0.0, ["No opposing pitcher context available -- matchup adjustment skipped"])

    ranges = _BATTER_RANGES["matchup"]
    weights = _BATTER_WEIGHTS["matchup"]

    pitcher_components = {
        "pitcher_k_percent": _normalize(opp.k_percent, **ranges["pitcher_k_percent"]),
        "pitcher_xwoba_allowed": _normalize(opp.xwoba_allowed, **ranges["pitcher_xwoba_allowed"]),
        "pitcher_hard_hit_allowed": _normalize(opp.hard_hit_percent_allowed, **ranges["pitcher_hard_hit_allowed"]),
    }
    pitcher_quality_index = _weighted_favorability(
        pitcher_components, {k: weights[k] for k in pitcher_components}
    )

    platoon = None
    if opp.throwing_hand == "L":
        platoon = b.vs_lhp
    elif opp.throwing_hand == "R":
        platoon = b.vs_rhp
    platoon_index = _normalize(platoon.woba, **ranges["platoon_woba"]) if platoon is not None else None

    if pitcher_quality_index is None and platoon_index is None:
        return AdjustmentResult(0.0, ["Opposing pitcher context present but no usable matchup fields"])

    reasons: List[str] = []
    if pitcher_quality_index is not None and platoon_index is not None:
        combined = (1 - cfg.PLATOON_WEIGHT) * pitcher_quality_index + cfg.PLATOON_WEIGHT * platoon_index
        reasons.append(
            f"Matchup: opposing-pitcher-quality index {pitcher_quality_index:.2f} blended with platoon "
            f"({opp.throwing_hand}HP) index {platoon_index:.2f} at {cfg.PLATOON_WEIGHT:.0%} platoon weight"
        )
    elif pitcher_quality_index is not None:
        combined = pitcher_quality_index
        reasons.append(f"Matchup: opposing-pitcher-quality index {pitcher_quality_index:.2f} (no platoon split data)")
    else:
        combined = platoon_index
        reasons.append(f"Matchup: platoon index {platoon_index:.2f} only (opposing pitcher quality data unavailable)")

    points = _points_from_favorability(combined, cfg.MATCHUP_HITTER_MAX_POINTS)
    return AdjustmentResult(round(points, 3), reasons)


# ----------------------------------------------------------------------------
# Pitcher vs. opposing lineup
# ----------------------------------------------------------------------------


def build_opposing_lineup_index(batter_inputs: List[BatterInput]) -> Dict[str, OpposingLineupQuality]:
    by_team: Dict[str, List[BatterInput]] = {}
    for b in batter_inputs:
        if b.batting_order is None:
            continue
        by_team.setdefault(b.team, []).append(b)

    index: Dict[str, OpposingLineupQuality] = {}
    for team, hitters in by_team.items():
        k_values = [h.season.k_percent for h in hitters if h.season.k_percent is not None]
        bb_values = [h.season.bb_percent for h in hitters if h.season.bb_percent is not None]
        iso_values = [h.season.iso for h in hitters if h.season.iso is not None]
        woba_values = [(h.season.woba if h.season.woba is not None else h.season.xwoba) for h in hitters]
        woba_values = [v for v in woba_values if v is not None]
        index[team] = OpposingLineupQuality(
            team=team,
            hitters_count=len(hitters),
            avg_k_percent=(sum(k_values) / len(k_values)) if k_values else None,
            avg_bb_percent=(sum(bb_values) / len(bb_values)) if bb_values else None,
            avg_iso=(sum(iso_values) / len(iso_values)) if iso_values else None,
            avg_woba=(sum(woba_values) / len(woba_values)) if woba_values else None,
            is_partial=len(hitters) < cfg.OPPOSING_LINEUP_MIN_HITTERS_FOR_AGGREGATE,
        )
    return index


def pitcher_matchup_adjustment(p: PitcherInput, opposing_lineup: Optional[OpposingLineupQuality]) -> AdjustmentResult:
    if opposing_lineup is None:
        return AdjustmentResult(0.0, ["No confirmed opposing lineup data available -- matchup adjustment skipped"])
    if opposing_lineup.is_partial:
        return AdjustmentResult(
            0.0,
            [
                f"Only {opposing_lineup.hitters_count} confirmed opposing hitters "
                f"(need {cfg.OPPOSING_LINEUP_MIN_HITTERS_FOR_AGGREGATE}) -- matchup adjustment skipped"
            ],
        )

    ranges = _PITCHER_RANGES["matchup"]
    weights = _PITCHER_WEIGHTS["matchup"]
    components = {
        "opponent_k_percent": _normalize(opposing_lineup.avg_k_percent, **ranges["opponent_k_percent"]),
        "opponent_woba": _normalize(opposing_lineup.avg_woba, **ranges["opponent_woba"]),
        "opponent_iso": _normalize(opposing_lineup.avg_iso, **ranges["opponent_iso"]),
    }
    favorability = _weighted_favorability(components, {k: weights[k] for k in components})
    if favorability is None:
        return AdjustmentResult(0.0, ["Opposing lineup aggregate present but no usable rate fields"])

    points = _points_from_favorability(favorability, cfg.MATCHUP_PITCHER_MAX_POINTS)
    reasons = [
        f"Matchup: opposing lineup quality index {favorability:.2f} from {opposing_lineup.hitters_count} "
        f"confirmed hitters (avg K% {opposing_lineup.avg_k_percent}, avg wOBA {opposing_lineup.avg_woba})"
    ]
    return AdjustmentResult(round(points, 3), reasons)


# ----------------------------------------------------------------------------
# Game environment (park / Vegas / weather / bullpen)
# ----------------------------------------------------------------------------


def environment_adjustment(
    player_type: str,
    park_factor: Optional[float] = None,
    team_implied_runs: Optional[float] = None,
    vegas_is_mock: Optional[bool] = None,
    weather_favors: Optional[List[str]] = None,
    weather_is_mock: Optional[bool] = None,
    opposing_bullpen_strength: Optional[float] = None,
    bullpen_is_mock: Optional[bool] = None,
) -> AdjustmentResult:
    """`team_implied_runs` is the run total relevant to THIS player's
    fantasy outcome -- the hitter's own team's implied runs, or (for a
    pitcher) the OPPONENT's implied runs. `weather_favors` is the list of
    WeatherAnalysis conclusion `favors` strings ("hitter"/"pitcher"/
    "neutral"/"risk") for this game. `opposing_bullpen_strength` is only
    meaningful for hitters (their opponent's bullpen); pitchers pass None."""
    reasons: List[str] = []
    points = 0.0

    if park_factor is not None:
        coefficient = cfg.PARK_HITTER_POINTS_PER_FACTOR_POINT if player_type == "hitter" else cfg.PARK_PITCHER_POINTS_PER_FACTOR_POINT
        park_points = (park_factor - 100.0) * coefficient
        points += park_points
        reasons.append(f"Park factor {park_factor:.0f} (real) -> {park_points:+.3f} points")

    if team_implied_runs is not None:
        # Safe-by-default: only an EXPLICIT vegas_is_mock=False (a real
        # provider actually said so) unlocks real weight. Unknown
        # provenance (None) is treated the same as mock -- never assume
        # data is real just because nobody said it was fake.
        if vegas_is_mock is not False:
            # Milestone 24: mock Vegas data must NEVER influence a
            # projection labeled real/live -- it may still be displayed
            # elsewhere in explicit dev/mock mode, but it contributes
            # ZERO points here, full stop (not merely "capped small" as
            # in the pre-M24 design).
            reasons.append(
                f"Vegas implied runs {team_implied_runs:.2f} (synthetic mock provider) -> +0.000 points "
                f"(mock Vegas never influences a real/live projection)"
            )
        else:
            runs_range = _PITCHER_RANGES["run_prevention"]["implied_runs"]  # {"low":3.0,"high":5.5,"invert":True} -- shared run-environment scale
            invert = player_type == "pitcher"
            favorability = _normalize(team_implied_runs, runs_range["low"], runs_range["high"], invert)
            vegas_points = _points_from_favorability(favorability, cfg.REAL_VEGAS_MAX_POINTS)
            points += vegas_points
            reasons.append(f"Vegas implied runs {team_implied_runs:.2f} (real market data) -> {vegas_points:+.3f} points")

    if weather_favors:
        other_type = "pitcher" if player_type == "hitter" else "hitter"
        favorable = sum(1 for f in weather_favors if f == player_type)
        unfavorable = sum(1 for f in weather_favors if f == other_type)
        total = len(weather_favors)
        if total > 0 and (favorable or unfavorable):
            net = (favorable - unfavorable) / total
            weather_points = net * cfg.MOCK_WEATHER_MAX_POINTS
            points += weather_points
            tag = "real" if weather_is_mock is False else "synthetic mock provider"
            reasons.append(
                f"Weather ({tag}): {favorable} conclusion(s) favor {player_type}, {unfavorable} favor {other_type} "
                f"-> {weather_points:+.3f} points"
            )

    if player_type == "hitter" and opposing_bullpen_strength is not None:
        favorability = _normalize(opposing_bullpen_strength, BULLPEN_STRENGTH_WEAK, BULLPEN_STRENGTH_ELITE, invert=True)
        bullpen_points = _points_from_favorability(favorability, cfg.MOCK_BULLPEN_MAX_POINTS)
        points += bullpen_points
        tag = "real" if bullpen_is_mock is False else "synthetic mock provider"
        reasons.append(f"Opposing bullpen strength {opposing_bullpen_strength:.0f} ({tag}) -> {bullpen_points:+.3f} points")

    if not reasons:
        reasons.append("No environment data available")

    return AdjustmentResult(round(points, 3), reasons)
