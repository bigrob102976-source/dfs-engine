"""A clearly-labeled MOCK EXTERNAL PROJECTIONS provider -- NOT real
BlueCollar (or any other real vendor's) data. Used only so the
baseline-snapshot / adjustment-engine / comparison-column / optimizer-
source-selector pipeline can be exercised end-to-end while BlueCollar
itself remains disabled (see external_projections/bluecollar_provider.py).

Player IDENTITY (name, team, opponent) is built entirely from the REAL
Research Package for the date -- nothing about who's playing is
invented, exactly like dfs/providers/mock_provider.py. PROJECTION is
the one field with no real external source available here: it is a
deterministic function of each player's own already-computed
independent projection (from the real Pitcher/Batter Agent snapshot),
perturbed by a fixed, reproducible +/-12% multiplier derived from the
player's id -- documented synthetic variance, not a random guess and
never claimed to be a genuine third-party projection. Every player and
slate returned by this provider is labeled `provider_name="MOCK
EXTERNAL PROJECTIONS"` so it can never be mistaken for real BlueCollar
data downstream (the merge step, the dashboard).
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dfs.snapshot_selection import select_snapshot
from external_projections.base import ProjectionProvider, ProjectionProviderUnavailableError
from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo
from research.adapters import pitcher_input as pitcher_adapter
from research.adapters.pitcher_input import ResearchPackageNotFoundError

_SLATE_ID_PREFIX = "mock-external"
_MOCK_PERTURBATION_RANGE = 0.12  # +/- 12%, fixed documented synthetic variance


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slate_id_for(date: str) -> str:
    return f"{_SLATE_ID_PREFIX}-{date}"


def _date_from_slate_id(slate_id: str) -> Optional[str]:
    if not slate_id.startswith(f"{_SLATE_ID_PREFIX}-"):
        return None
    return slate_id[len(_SLATE_ID_PREFIX) + 1:]


def _mock_multiplier(player_id: str) -> float:
    """Deterministic pseudo-random multiplier in
    [1 - _MOCK_PERTURBATION_RANGE, 1 + _MOCK_PERTURBATION_RANGE], stable
    across repeated calls for the same player_id (never real randomness)."""
    digest = hashlib.md5(f"mock-external-projection-{player_id}".encode("utf-8")).hexdigest()
    fraction = int(digest[:8], 16) / 0xFFFFFFFF  # deterministic, in [0, 1]
    return 1.0 + (fraction * 2 - 1) * _MOCK_PERTURBATION_RANGE


def _mock_project(player_id: str, value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(value * _mock_multiplier(player_id), 2)


class MockExternalProvider(ProjectionProvider):
    """Development/mock EXTERNAL PROJECTION provider -- see module docstring."""

    name = "mock_external_projections"
    is_mock = True

    def __init__(self, research_output_root: str = "research_output", predictions_root: str = "predictions"):
        self.research_output_root = research_output_root
        self.predictions_root = predictions_root

    def provider_name(self) -> str:
        return "MOCK EXTERNAL PROJECTIONS"

    def provider_version(self) -> Optional[str]:
        return "mock-1.0"

    def is_configured(self) -> bool:
        return True

    def list_slates(self, date: str, sport: str = "MLB", site: str = "draftkings") -> List[ExternalSlateInfo]:
        if sport.upper() != "MLB":
            return []
        try:
            pitcher_pkg = pitcher_adapter.load_research_package(self.research_output_root, date)
        except ResearchPackageNotFoundError as e:
            raise ProjectionProviderUnavailableError(
                f"No Research Package found for {date} under {self.research_output_root}/ -- build it first."
            ) from e

        games_by_id = {g["game_id"]: g for g in pitcher_pkg["games"]}
        if not games_by_id:
            return []
        return [ExternalSlateInfo(
            slate_id=_slate_id_for(date), slate_name="Mock External Main", sport=sport, site=site,
            player_count=None,
        )]

    def get_projections(self, slate_id: str) -> List[ExternalProjectionPlayer]:
        date = _date_from_slate_id(slate_id)
        if date is None:
            raise ProjectionProviderUnavailableError(f"Unrecognized mock external slate id: {slate_id!r}")

        pitcher_snapshot, _ = select_snapshot(None, date, Path(self.predictions_root), "pitcher_board")
        batter_snapshot, _ = select_snapshot(None, date, Path(self.predictions_root), "batter_board")
        if pitcher_snapshot is None and batter_snapshot is None:
            raise ProjectionProviderUnavailableError(
                f"No pitcher or batter snapshot found for {date} under {self.predictions_root}/ -- "
                f"run the Pitcher/Batter Agent first."
            )

        retrieved_at = _now()
        players: List[ExternalProjectionPlayer] = []

        for p in (pitcher_snapshot or {}).get("pitchers", []):
            projection = p.get("projection")
            if projection is None:
                continue
            players.append(ExternalProjectionPlayer(
                external_player_id=f"mock-ext-{p['player_id']}", name=p["name"], team=p["team"],
                opponent=p.get("opponent"), position="P", salary=None,
                projection=_mock_project(p["player_id"], projection),
                ceiling=_mock_project(p["player_id"], p.get("ceiling")),
                floor=_mock_project(p["player_id"], p.get("floor")),
                ownership_projection=None, slate_id=slate_id, slate_name="Mock External Main",
                updated_at=retrieved_at, provider_name=self.provider_name(), provider_version=self.provider_version(),
            ))

        for h in (batter_snapshot or {}).get("hitters", []):
            projection = h.get("projection")
            if projection is None:
                continue
            players.append(ExternalProjectionPlayer(
                external_player_id=f"mock-ext-{h['player_id']}", name=h["name"], team=h["team"],
                opponent=h.get("opponent"), position=h.get("position") or "OF", salary=None,
                projection=_mock_project(h["player_id"], projection),
                ceiling=_mock_project(h["player_id"], h.get("ceiling")),
                floor=_mock_project(h["player_id"], h.get("floor")),
                ownership_projection=None, slate_id=slate_id, slate_name="Mock External Main",
                updated_at=retrieved_at, provider_name=self.provider_name(), provider_version=self.provider_version(),
            ))

        return players
