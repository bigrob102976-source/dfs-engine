"""Umpire research model for the Game Environment Engine (Milestone DS2).

Research model only -- no live umpire-assignment feed is configured or
credentialed in this environment. Every real (non-mock) lookup honestly
reports status="UNKNOWN" rather than guessing which umpire is working a
game or fabricating their tendencies. Only the clearly-labeled
MockUmpireProvider (used for tests and live-validation demos) ever
returns a KNOWN profile.
"""

import hashlib
from abc import ABC, abstractmethod

from research.game_environment.models import UmpireProfile


class UmpireProvider(ABC):
    name: str = "unnamed_provider"
    is_mock: bool = False

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_umpire(self, game_id: str) -> UmpireProfile:
        """Never raises -- an unavailable umpire is a normal outcome
        represented by status="UNKNOWN", not an error."""
        raise NotImplementedError


class UnknownUmpireProvider(UmpireProvider):
    """The default, real-world provider: no umpire-assignment data
    source exists, so every game honestly reports UNKNOWN. This is the
    provider used whenever no explicit provider is configured (see
    collector.py) -- never a silent guess."""

    name = "unknown_umpire_provider"
    is_mock = False

    def provider_name(self) -> str:
        return "No Umpire Data Source Configured"

    def is_configured(self) -> bool:
        return False

    def get_umpire(self, game_id: str) -> UmpireProfile:
        return UmpireProfile(game_id=game_id, status="UNKNOWN", tendency="unknown")


def _seeded_fraction(seed: str) -> float:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class MockUmpireProvider(UmpireProvider):
    """Development/mock umpire provider -- see module docstring.
    Deterministic per game_id, clearly labeled, never presented as a
    real umpire assignment."""

    name = "mock_umpire_provider"
    is_mock = True

    def provider_name(self) -> str:
        return "MOCK UMPIRE DATA"

    def is_configured(self) -> bool:
        return True

    def get_umpire(self, game_id: str) -> UmpireProfile:
        strike_pct = round(61.0 + _seeded_fraction(f"{game_id}-strike") * 6.0, 1)  # 61-67%
        walk_pct = round(7.5 + _seeded_fraction(f"{game_id}-walk") * 3.0, 1)  # 7.5-10.5%
        k_pct = round(20.0 + _seeded_fraction(f"{game_id}-k") * 8.0, 1)  # 20-28%
        zone_size = round(_seeded_fraction(f"{game_id}-zone") * 100.0, 1)
        runs_per_game = round(8.0 + (_seeded_fraction(f"{game_id}-runs") - 0.5) * 2.0, 2)  # ~7-9

        if zone_size >= 60:
            tendency = "pitcher_friendly"
        elif zone_size <= 40:
            tendency = "hitter_friendly"
        else:
            tendency = "neutral"

        return UmpireProfile(
            game_id=game_id, status="KNOWN", name=f"Mock Umpire #{int(_seeded_fraction(game_id) * 90) + 10}",
            strike_percent=strike_pct, walk_percent=walk_pct, k_percent=k_pct, zone_size_score=zone_size,
            runs_per_game=runs_per_game, tendency=tendency,
        )
