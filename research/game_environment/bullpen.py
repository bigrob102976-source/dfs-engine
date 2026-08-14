"""Bullpen research + strength scoring for the Game Environment Engine
(Milestone DS2).

Same data-source discipline as weather.py/vegas.py: no real bullpen
usage/fatigue feed is configured or credentialed in this environment --
only the clearly-labeled MockBullpenProvider is registered today.
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Optional

from config.game_environment_config import BULLPEN_ERA_STRONG, BULLPEN_ERA_WEAK, FATIGUE_HIGH_RELIEVERS_USED
from research.game_environment.models import BullpenProfile


class BullpenProviderNotConfiguredError(RuntimeError):
    """No real bullpen data provider is configured -- a normal,
    expected state today, not a failure."""


class BullpenProvider(ABC):
    name: str = "unnamed_provider"
    is_mock: bool = False

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_bullpen(self, team_abbr: str) -> BullpenProfile:
        raise NotImplementedError


def _seeded_fraction(seed: str) -> float:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def score_bullpen_strength(era: Optional[float], fip: Optional[float], relievers_used_last_3_days: Optional[int], closer_available: Optional[bool]) -> Optional[float]:
    """0-100, higher = stronger bullpen (worse for opposing hitters).
    Blends whichever inputs are available and renormalizes -- same
    discipline as config/scoring_config.py's COMPONENT_WEIGHTS. Returns
    None only when NOTHING is available to score."""
    parts = []
    weights = []

    # BULLPEN_ERA_STRONG maps to a top score, BULLPEN_ERA_WEAK to a
    # bottom score, linear between (and clamped beyond) -- one shared
    # band for both ERA and FIP, since both are earned-run-rate stats.
    band_low, band_high = BULLPEN_ERA_STRONG, BULLPEN_ERA_WEAK

    if era is not None:
        score = max(0.0, min(100.0, (band_high - era) / (band_high - band_low) * 100.0))
        parts.append(score)
        weights.append(0.5)

    if fip is not None:
        score = max(0.0, min(100.0, (band_high - fip) / (band_high - band_low) * 100.0))
        parts.append(score)
        weights.append(0.3)

    if relievers_used_last_3_days is not None:
        # More relievers used recently -> more fatigued -> weaker.
        score = max(0.0, min(100.0, 100.0 - (relievers_used_last_3_days / 8.0) * 100.0))
        parts.append(score)
        weights.append(0.1)

    if closer_available is not None:
        parts.append(100.0 if closer_available else 40.0)
        weights.append(0.1)

    if not parts:
        return None

    total_weight = sum(weights)
    return round(sum(p * w for p, w in zip(parts, weights)) / total_weight, 1)


def fatigue_label(relievers_used_last_3_days: Optional[int]) -> str:
    if relievers_used_last_3_days is None:
        return "unknown"
    if relievers_used_last_3_days >= FATIGUE_HIGH_RELIEVERS_USED:
        return "high"
    if relievers_used_last_3_days >= 1:
        return "medium"
    return "low"


class MockBullpenProvider(BullpenProvider):
    """Development/mock bullpen provider -- see module docstring.
    Deterministic per team_abbr, clearly labeled, never presented as
    real usage data."""

    name = "mock_bullpen_provider"
    is_mock = True

    def provider_name(self) -> str:
        return "MOCK BULLPEN DATA"

    def is_configured(self) -> bool:
        return True

    def get_bullpen(self, team_abbr: str) -> BullpenProfile:
        era = round(3.00 + _seeded_fraction(f"{team_abbr}-era") * 2.50, 2)  # 3.00-5.50
        fip = round(3.00 + _seeded_fraction(f"{team_abbr}-fip") * 2.50, 2)
        xfip = round(3.00 + _seeded_fraction(f"{team_abbr}-xfip") * 2.50, 2)
        relievers_used = int(_seeded_fraction(f"{team_abbr}-relievers") * 6.0)  # 0-5
        closer_available = _seeded_fraction(f"{team_abbr}-closer") >= 0.2  # mostly available
        high_leverage = int(_seeded_fraction(f"{team_abbr}-leverage") * 4.0)  # 0-3

        strength = score_bullpen_strength(era, fip, relievers_used, closer_available)

        return BullpenProfile(
            team_abbr=team_abbr, provider_name=self.provider_name(), is_mock=True,
            era=era, fip=fip, xfip=xfip, relievers_used_last_3_days=relievers_used,
            estimated_fatigue=fatigue_label(relievers_used), closer_available=closer_available,
            high_leverage_arms_available=high_leverage, strength_score=strength,
        )
