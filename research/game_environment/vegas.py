"""Vegas odds collection + deterministic slate-wide analysis for the
Game Environment Engine (Milestone DS2).

Same data-source discipline as weather.py: no real odds API is
configured or credentialed in this environment -- only the
clearly-labeled MockVegasProvider is registered today.
"""

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from config.game_environment_config import (
    LINE_MOVEMENT_SHARP_RUNS,
    TOTAL_HIGH_THRESHOLD,
    TOTAL_LOW_THRESHOLD,
)
from research.game_environment.models import VegasLine, VegasSlateAnalysis, VegasSnapshot


class VegasProviderNotConfiguredError(RuntimeError):
    """No real Vegas odds provider is configured -- a normal, expected
    state today, not a failure."""


class VegasProviderUnavailableError(RuntimeError):
    """The provider is configured but unreachable/erroring."""


class VegasProvider(ABC):
    name: str = "unnamed_provider"
    is_mock: bool = False

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_vegas_line(self, game_id: str, home_team_abbr: str, away_team_abbr: str) -> VegasSnapshot:
        raise NotImplementedError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seeded_fraction(seed: str) -> float:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _moneyline_to_win_probability(moneyline: int) -> float:
    if moneyline < 0:
        return (-moneyline) / ((-moneyline) + 100)
    return 100 / (moneyline + 100)


class MockVegasProvider(VegasProvider):
    """Development/mock Vegas odds provider -- see module docstring.
    Deterministic per game_id, clearly labeled, never presented as a
    real market price."""

    name = "mock_vegas_provider"
    is_mock = True

    def provider_name(self) -> str:
        return "MOCK VEGAS"

    def is_configured(self) -> bool:
        return True

    def get_vegas_line(self, game_id: str, home_team_abbr: str, away_team_abbr: str) -> VegasSnapshot:
        opening_total = round(7.0 + _seeded_fraction(f"{game_id}-total") * 5.0, 1)  # 7.0-12.0
        total_drift = round((_seeded_fraction(f"{game_id}-drift") - 0.5) * 1.6, 1)  # -0.8..+0.8
        current_total = round(opening_total + total_drift, 1)

        # Home moneyline: favorite or underdog, deterministic per game.
        home_is_favorite = _seeded_fraction(f"{game_id}-favorite") >= 0.5
        magnitude = int(110 + _seeded_fraction(f"{game_id}-magnitude") * 140)  # 110-250
        opening_home_ml = -magnitude if home_is_favorite else magnitude
        opening_away_ml = magnitude if home_is_favorite else -magnitude
        ml_drift = int((_seeded_fraction(f"{game_id}-ml-drift") - 0.5) * 40)  # -20..+20
        current_home_ml = opening_home_ml + ml_drift
        current_away_ml = -current_home_ml if abs(current_home_ml) > 100 else opening_away_ml

        home_win_prob = _moneyline_to_win_probability(current_home_ml)
        away_win_prob = 1.0 - home_win_prob
        # A favorite is also expected to score a modestly larger share of the total.
        home_implied = round(current_total * (0.5 + (home_win_prob - 0.5) * 0.3), 2)
        away_implied = round(current_total - home_implied, 2)

        run_line_home = -1.5 if home_is_favorite else 1.5
        run_line_away = -run_line_home

        retrieved_at = _now()
        return VegasSnapshot(
            game_id=game_id, home_team=home_team_abbr, away_team=away_team_abbr,
            provider_name=self.provider_name(), is_mock=True, retrieved_at=retrieved_at,
            opening_home=VegasLine(moneyline=opening_home_ml, run_line=run_line_home, total=opening_total),
            opening_away=VegasLine(moneyline=opening_away_ml, run_line=run_line_away, total=opening_total),
            current_home=VegasLine(moneyline=current_home_ml, run_line=run_line_home, total=current_total),
            current_away=VegasLine(moneyline=current_away_ml, run_line=run_line_away, total=current_total),
            home_implied_runs=home_implied, away_implied_runs=away_implied,
            total_movement=round(current_total - opening_total, 1),
            moneyline_movement_home=current_home_ml - opening_home_ml,
        )


def analyze_vegas_slate(snapshots: List[VegasSnapshot]) -> VegasSlateAnalysis:
    """Deterministic slate-wide Vegas conclusions -- computed once
    across every game with a snapshot, never per-game."""
    if not snapshots:
        return VegasSlateAnalysis()

    def total_of(s: VegasSnapshot) -> float:
        return s.current_home.total if s.current_home.total is not None else -1.0

    def abs_movement(s: VegasSnapshot) -> float:
        return abs(s.total_movement) if s.total_movement is not None else 0.0

    def home_favorite_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_home.moneyline
        return -ml if ml is not None and ml < 0 else -10_000

    def home_underdog_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_home.moneyline
        return ml if ml is not None and ml > 0 else -10_000

    def away_favorite_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_away.moneyline
        return -ml if ml is not None and ml < 0 else -10_000

    def away_underdog_magnitude(s: VegasSnapshot) -> int:
        ml = s.current_away.moneyline
        return ml if ml is not None and ml > 0 else -10_000

    highest = max(snapshots, key=total_of)
    lowest = min(snapshots, key=total_of)
    largest_move = max(snapshots, key=abs_movement)

    favorite_candidates = [(max(home_favorite_magnitude(s), away_favorite_magnitude(s)), s) for s in snapshots]
    biggest_favorite = max(favorite_candidates, key=lambda pair: pair[0])[1]

    underdog_candidates = [(max(home_underdog_magnitude(s), away_underdog_magnitude(s)), s) for s in snapshots]
    biggest_underdog = max(underdog_candidates, key=lambda pair: pair[0])[1]

    sharp = [s.game_id for s in snapshots if abs_movement(s) >= LINE_MOVEMENT_SHARP_RUNS]

    return VegasSlateAnalysis(
        highest_total_game_id=highest.game_id,
        lowest_total_game_id=lowest.game_id,
        largest_movement_game_id=largest_move.game_id if abs_movement(largest_move) > 0 else None,
        biggest_favorite_game_id=biggest_favorite.game_id,
        biggest_underdog_game_id=biggest_underdog.game_id,
        sharp_movement_game_ids=sharp,
    )


def total_tier(total: Optional[float]) -> str:
    """"high" | "low" | "medium" -- used by scoring.py and the dashboard
    filter for "Highest Totals"."""
    if total is None:
        return "medium"
    if total >= TOTAL_HIGH_THRESHOLD:
        return "high"
    if total <= TOTAL_LOW_THRESHOLD:
        return "low"
    return "medium"
