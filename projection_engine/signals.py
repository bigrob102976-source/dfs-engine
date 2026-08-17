"""Raw (pre-weight) signal extraction for the AI Projection Engine.

Every function here reads fields ALREADY computed by an existing agent
or engine -- research/game_environment/weather.py's WeatherConclusion,
research/game_environment/vegas.py's total_tier/implied runs,
research/game_environment/bullpen.py's strength_score,
research/game_environment/ballpark.py's static hr_factor,
ownership/leverage.py's leverage_score, or the Pitcher/Batter Agent's
own matchup_score/recent_trend_score/tags -- and turns them into a
single UN-weighted point delta with a human-readable reason. Nothing
here re-derives wind direction, implied runs, bullpen strength, park
factors, ownership, or matchup quality; weights.py applies
config-driven weights on top of what's returned here.

A signal that has nothing to say (missing upstream data, or a neutral
reading) returns None -- never a fabricated 0.0 "signal" with an empty
reason.
"""

from typing import List, Optional

from config.projection_engine_config import (
    BULLPEN_FATIGUE_HIGH_HITTER_BONUS_POINTS,
    BULLPEN_HITTER_ELITE_OPPONENT_BULLPEN_POINTS,
    BULLPEN_HITTER_WEAK_OPPONENT_BULLPEN_POINTS,
    BULLPEN_PITCHER_ELITE_OWN_BULLPEN_POINTS,
    BULLPEN_PITCHER_WEAK_OWN_BULLPEN_POINTS,
    BULLPEN_STRENGTH_ELITE,
    BULLPEN_STRENGTH_WEAK,
    MATCHUP_NEUTRAL_SCORE,
    MATCHUP_POINTS_PER_SCORE_POINT,
    OWNERSHIP_CHALK_FADE_POINTS,
    OWNERSHIP_CHALK_FADE_THRESHOLD_PERCENT,
    OWNERSHIP_LEVERAGE_BONUS_POINTS,
    OWNERSHIP_LEVERAGE_BONUS_THRESHOLD,
    PARK_HITTER_POINTS_PER_HR_FACTOR_POINT,
    PARK_HR_FACTOR_NEUTRAL,
    PARK_PITCHER_POINTS_PER_HR_FACTOR_POINT,
    RECENT_FORM_NEUTRAL_SCORE,
    RECENT_FORM_PITCHER_TAG_POINTS,
    RECENT_FORM_POINTS_PER_SCORE_POINT,
    VEGAS_HIGH_TOTAL_POINTS,
    VEGAS_LOW_TOTAL_POINTS,
    VEGAS_MOVEMENT_MAX_POINTS,
    VEGAS_MOVEMENT_POINTS_PER_RUN,
    WEATHER_CONCLUSION_POINTS,
    WEATHER_RISK_CODES,
)
from projection_engine.models import RawSignal
from research.game_environment.vegas import total_tier


def _wind_direction_word(code: str) -> str:
    if code.endswith("_out"):
        return "Wind Out"
    if code.endswith("_in"):
        return "Wind In"
    return "Wind"


def weather_signal(player_type: str, weather: Optional[dict], weather_analysis: Optional[dict]) -> Optional[RawSignal]:
    """Reuses WeatherAnalysis.conclusions verbatim -- codes/favors are
    already deterministic classifications from weather.py::analyze_weather."""
    if not weather_analysis or not weather_analysis.get("conclusions"):
        return None

    wind_speed = None
    if weather and weather.get("current"):
        wind_speed = weather["current"].get("wind_speed_mph")

    total_delta = 0.0
    reasons: List[str] = []
    for conclusion in weather_analysis["conclusions"]:
        code = conclusion.get("code")
        favors = conclusion.get("favors")
        if code in WEATHER_RISK_CODES or favors not in ("hitter", "pitcher"):
            continue  # risk conclusions feed AI Risk, not the projection -- see weights.py
        points = WEATHER_CONCLUSION_POINTS.get(code)
        if not points:
            continue
        sign = 1.0 if favors == player_type else -1.0
        total_delta += sign * points
        if "wind" in code and wind_speed is not None:
            reasons.append(f"{_wind_direction_word(code)} {wind_speed:.0f} MPH")
        else:
            reasons.append(conclusion.get("text") or code)

    if not reasons:
        return None
    return RawSignal(category="weather", label="Weather", raw_delta=round(total_delta, 3), reason="; ".join(reasons))


def vegas_signal(player_type: str, is_home: bool, vegas: Optional[dict]) -> Optional[RawSignal]:
    """Reuses VegasSnapshot's own home_implied_runs/away_implied_runs/
    total_movement and vegas.py::total_tier -- never re-derives odds math.

    Milestone 24: mock Vegas data must never influence a production/live
    AI projection (same provenance rule as native_projections/matchup.py
    ::environment_adjustment) -- returns None (no signal at all) whenever
    `vegas["is_mock"]` is true, or whenever provenance is unknown
    (key absent), treating "unknown" the same as "mock" rather than
    assuming real. This is an input-quality/provenance fix, not a weight
    change -- VEGAS_HIGH_TOTAL_POINTS/VEGAS_LOW_TOTAL_POINTS/etc. in
    config/projection_engine_config.py are untouched."""
    if not vegas or vegas.get("is_mock", True) is not False:
        return None

    implied = vegas.get("home_implied_runs") if is_home else vegas.get("away_implied_runs")
    current_home = vegas.get("current_home") or {}
    tier = total_tier(current_home.get("total"))

    delta = 0.0
    reasons: List[str] = []

    if tier == "high":
        sign = 1.0 if player_type == "hitter" else -1.0
        delta += sign * VEGAS_HIGH_TOTAL_POINTS
        reasons.append(f"Own team implied {implied:.1f} runs in a high-total game" if implied is not None else "High-total tier game")
    elif tier == "low":
        sign = -1.0 if player_type == "hitter" else 1.0
        delta += sign * VEGAS_LOW_TOTAL_POINTS
        reasons.append(f"Own team implied {implied:.1f} runs in a low-total game" if implied is not None else "Low-total tier game")

    movement = vegas.get("total_movement")
    if movement:
        movement_points = min(abs(movement) * VEGAS_MOVEMENT_POINTS_PER_RUN, VEGAS_MOVEMENT_MAX_POINTS)
        favors_hitter = movement > 0
        sign = 1.0 if favors_hitter == (player_type == "hitter") else -1.0
        delta += sign * movement_points
        direction = "up" if movement > 0 else "down"
        reasons.append(f"Total moved {direction} {abs(movement):.1f} runs since open")

    if not reasons:
        return None
    return RawSignal(category="vegas", label="Vegas", raw_delta=round(delta, 3), reason="; ".join(reasons))


def bullpen_signal(player_type: str, is_home: bool, bullpen_home: Optional[dict], bullpen_away: Optional[dict]) -> Optional[RawSignal]:
    """Pitchers: their OWN bullpen (elite + rested raises hook risk).
    Hitters: the OPPOSING bullpen (weak/fatigued raises scoring upside).
    Reuses bullpen.py's own strength_score/estimated_fatigue verbatim."""
    own = bullpen_home if is_home else bullpen_away
    opponent = bullpen_away if is_home else bullpen_home
    target = own if player_type == "pitcher" else opponent

    if not target or target.get("strength_score") is None:
        return None

    strength = target["strength_score"]
    fatigue = target.get("estimated_fatigue")
    delta = 0.0
    reasons: List[str] = []

    if player_type == "pitcher":
        if strength >= BULLPEN_STRENGTH_ELITE and fatigue in ("low", "medium"):
            delta += BULLPEN_PITCHER_ELITE_OWN_BULLPEN_POINTS
            reasons.append(f"Elite, rested own bullpen (strength {strength:.0f}) raises hook risk")
        elif strength <= BULLPEN_STRENGTH_WEAK:
            delta += BULLPEN_PITCHER_WEAK_OWN_BULLPEN_POINTS
            reasons.append(f"Weak own bullpen (strength {strength:.0f}) suggests a longer leash")
    else:
        if strength <= BULLPEN_STRENGTH_WEAK:
            delta += BULLPEN_HITTER_WEAK_OPPONENT_BULLPEN_POINTS
            reasons.append(f"Weak opposing bullpen (strength {strength:.0f})")
        elif strength >= BULLPEN_STRENGTH_ELITE:
            delta += BULLPEN_HITTER_ELITE_OPPONENT_BULLPEN_POINTS
            reasons.append(f"Elite opposing bullpen (strength {strength:.0f})")
        if fatigue == "high":
            delta += BULLPEN_FATIGUE_HIGH_HITTER_BONUS_POINTS
            reasons.append("Opposing bullpen is highly fatigued")

    if not reasons:
        return None
    return RawSignal(category="bullpen", label="Bullpen", raw_delta=round(delta, 3), reason="; ".join(reasons))


def park_signal(player_type: str, ballpark: Optional[dict]) -> Optional[RawSignal]:
    """Reuses ballpark.py's static, publicly-known hr_factor (100 =
    league-neutral) -- never re-derives park factors."""
    if not ballpark or ballpark.get("hr_factor") is None:
        return None

    hr_factor = ballpark["hr_factor"]
    diff = hr_factor - PARK_HR_FACTOR_NEUTRAL
    if diff == 0:
        return None

    per_point = PARK_HITTER_POINTS_PER_HR_FACTOR_POINT if player_type == "hitter" else PARK_PITCHER_POINTS_PER_HR_FACTOR_POINT
    delta = diff * per_point
    venue = ballpark.get("venue_name", "this park")
    descriptor = "Excellent" if diff >= 15 else "Strong" if diff >= 5 else "Below-average" if diff <= -5 else "Modest"
    reason = f"{descriptor} HR environment at {venue} (HR factor {hr_factor})"
    return RawSignal(category="park", label="Park", raw_delta=round(delta, 3), reason=reason)


def ownership_signal(ownership_row: Optional[dict]) -> Optional[RawSignal]:
    """Reuses ownership/leverage.py's own leverage_score and the
    Ownership model's projected_ownership -- never re-derives ownership.
    A small GPP-context nudge per CLAUDE.md's leverage-against-the-field
    mission, not a claim that ownership changes true expected points."""
    if not ownership_row:
        return None

    projected_ownership = ownership_row.get("projected_ownership")
    leverage_score = ownership_row.get("leverage_score")
    delta = 0.0
    reasons: List[str] = []

    if projected_ownership is not None and projected_ownership >= OWNERSHIP_CHALK_FADE_THRESHOLD_PERCENT:
        delta += OWNERSHIP_CHALK_FADE_POINTS
        reasons.append(f"Extremely popular tournament play ({projected_ownership:.1f}% projected owned)")
    if leverage_score is not None and leverage_score >= OWNERSHIP_LEVERAGE_BONUS_THRESHOLD:
        delta += OWNERSHIP_LEVERAGE_BONUS_POINTS
        reasons.append(f"Low-owned, high-leverage tournament play (leverage {leverage_score:.1f})")

    if not reasons:
        return None
    return RawSignal(category="ownership", label="Ownership", raw_delta=round(delta, 3), reason="; ".join(reasons))


def matchup_signal(board_record: dict) -> Optional[RawSignal]:
    """Reuses the Pitcher/Batter Agent's own matchup_score (0-100, 50 =
    neutral) -- never recomputes opponent quality."""
    score = board_record.get("matchup_score")
    if score is None:
        return None
    deviation = score - MATCHUP_NEUTRAL_SCORE
    if deviation == 0:
        return None
    delta = deviation * MATCHUP_POINTS_PER_SCORE_POINT
    descriptor = "Favorable" if deviation > 0 else "Difficult"
    reason = f"{descriptor} matchup (matchup score {score:.0f})"
    return RawSignal(category="matchup", label="Matchup", raw_delta=round(delta, 3), reason=reason)


def recent_form_signal(player_type: str, board_record: dict) -> Optional[RawSignal]:
    """Hitters: the Batter Agent's own recent_trend_score (0-100, 50 =
    neutral). Pitchers have no equivalent dedicated sub-score, so this
    reuses the Pitcher Agent's own positive_trend/negative_trend tags --
    never recomputes trend deltas."""
    if player_type == "hitter":
        score = board_record.get("recent_trend_score")
        if score is None:
            return None
        deviation = score - RECENT_FORM_NEUTRAL_SCORE
        if deviation == 0:
            return None
        delta = deviation * RECENT_FORM_POINTS_PER_SCORE_POINT
        descriptor = "improving" if deviation > 0 else "declining"
        reason = f"Recent form {descriptor} (trend score {score:.0f})"
        return RawSignal(category="recent_form", label="Recent Form", raw_delta=round(delta, 3), reason=reason)

    tags = board_record.get("tags") or []
    if "positive_trend" in tags:
        return RawSignal(category="recent_form", label="Recent Form", raw_delta=RECENT_FORM_PITCHER_TAG_POINTS, reason="Positive recent Statcast trend")
    if "negative_trend" in tags:
        return RawSignal(category="recent_form", label="Recent Form", raw_delta=-RECENT_FORM_PITCHER_TAG_POINTS, reason="Negative recent Statcast trend")
    return None


def external_gap_signal(independent_projection: Optional[float], external_projection: Optional[float]) -> Optional[RawSignal]:
    """Reuses the latest adjusted-projection snapshot's own
    independent_projection/external_projection pair -- never re-fetches
    or re-matches external data."""
    if independent_projection is None or external_projection is None:
        return None
    gap = external_projection - independent_projection
    if gap == 0:
        return None
    direction = "above" if gap > 0 else "below"
    reason = f"External model projects {abs(gap):.1f} points {direction} independent projection"
    return RawSignal(category="external", label="External Projection", raw_delta=round(gap, 3), reason=reason)
