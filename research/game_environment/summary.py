"""Deterministic AI game summary generation for the Game Environment
Engine (Milestone DS2).

Every bullet point is assembled from a fixed template keyed off an
already-computed threshold or conclusion -- there is no free-form LLM
text generation here, matching the milestone's explicit "No free-form
LLM text. Deterministic." instruction for weather analysis, extended to
the summary as a whole.
"""

from typing import List, Optional

from config.game_environment_config import TOTAL_HIGH_THRESHOLD, TOTAL_LOW_THRESHOLD
from research.game_environment.bullpen import BullpenProfile
from research.game_environment.models import BallparkProfile, EnvironmentScore, GameSummary, VegasSnapshot, WeatherAnalysis


def _environment_headline(overall: float) -> str:
    if overall >= 80:
        return "Excellent offensive environment."
    if overall >= 65:
        return "Strong offensive environment."
    if overall <= 20:
        return "Excellent pitcher's environment."
    if overall <= 35:
        return "Strong pitcher's environment."
    return "Balanced offensive environment."


def _bullpen_bullet(bullpen_home: Optional[BullpenProfile], bullpen_away: Optional[BullpenProfile]) -> Optional[str]:
    strengths = [bp.strength_score for bp in (bullpen_home, bullpen_away) if bp is not None and bp.strength_score is not None]
    if not strengths:
        return None
    avg = sum(strengths) / len(strengths)
    if avg <= 40:
        return "Weak bullpen."
    if avg >= 65:
        return "Strong bullpen."
    return None


def _park_bullet(park: Optional[BallparkProfile]) -> Optional[str]:
    if park is None:
        return None
    if park.park_factor >= 108:
        return "Hitter friendly park."
    if park.park_factor <= 92:
        return "Pitcher friendly park."
    return None


def _vegas_bullet(vegas: Optional[VegasSnapshot]) -> Optional[str]:
    if vegas is None or vegas.current_home.total is None:
        return None
    total = vegas.current_home.total
    if total >= TOTAL_HIGH_THRESHOLD:
        return "High implied total."
    if total <= TOTAL_LOW_THRESHOLD:
        return "Low implied total."
    return None


def generate_game_summary(
    home_team: str,
    away_team: str,
    environment_score: EnvironmentScore,
    weather_analysis: Optional[WeatherAnalysis],
    vegas: Optional[VegasSnapshot],
    park: Optional[BallparkProfile],
    bullpen_home: Optional[BullpenProfile],
    bullpen_away: Optional[BullpenProfile],
) -> GameSummary:
    headline = f"{away_team} @ {home_team}"
    bullets: List[str] = [_environment_headline(environment_score.overall)]

    had_risk_conclusion = False
    if weather_analysis is not None:
        for c in weather_analysis.conclusions:
            bullets.append(c.text)
            if c.favors == "risk":
                had_risk_conclusion = True
        if weather_analysis.conclusions and weather_analysis.conclusions[0].code != "indoor_game" and not had_risk_conclusion:
            bullets.append("No rain concerns.")

    vegas_bullet = _vegas_bullet(vegas)
    if vegas_bullet:
        bullets.append(vegas_bullet)

    bullpen_bullet = _bullpen_bullet(bullpen_home, bullpen_away)
    if bullpen_bullet:
        bullets.append(bullpen_bullet)

    park_bullet = _park_bullet(park)
    if park_bullet:
        bullets.append(park_bullet)

    return GameSummary(headline=headline, bullet_points=bullets)
