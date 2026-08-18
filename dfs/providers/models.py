"""Normalized data shapes every DFS salary provider must return.

Nothing downstream of dfs/providers/ (the fetch script, the pool
builder, the optimizer) should ever need to know which concrete
provider supplied this data -- see dfs/providers/base.py.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class ProviderPlayer:
    """One player as reported by a DFS salary provider for one slate.
    Salary/positions here are whatever the PROVIDER says -- this module
    never invents or adjusts them."""

    external_player_id: str
    name: str
    team: str
    opponent: Optional[str]
    game: Optional[str]  # "AWAY@HOME" team-pair, provider's own naming
    salary: int
    position_eligibility: List[str]
    slate_id: str
    slate_name: Optional[str]
    start_time: Optional[str]  # ISO-8601 if the provider exposes it
    source: str
    retrieved_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderSlateInfo:
    """One DFS slate the provider knows about for a given date (DK's
    "Main" / "Turbo" / "Late" concept, provider-agnostic).

    Milestone 26: `game_ids` is the field the rest of the dashboard
    filters every page by (Pitchers/Hitters/Vegas/Ownership/Native/AI/
    Optimizer) -- it resolves each of the provider's own raw
    "AWAY@HOME ..." game strings against the MLB Research Package via
    dfs/slate_validation.py::resolve_game_ids(). Populated only when a
    caller passes `research_games` into get_slate() (see
    dfs/providers/base.py); empty when no Research Package was available
    to resolve against, so callers must treat an empty list as "unknown",
    never "zero games on this slate"."""

    slate_id: str
    slate_name: Optional[str]
    site: str
    sport: str
    start_time: Optional[str]
    game_count: Optional[int]
    game_ids: List[str] = field(default_factory=list)
    player_count: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderSlateResult:
    """Everything a provider returned for one `get_slate()` call --
    every slate it found for that date/sport/site, and each slate's
    player list, keyed by slate_id."""

    slates: List[ProviderSlateInfo]
    players_by_slate: Dict[str, List[ProviderPlayer]]
    source: str
    retrieved_at: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slates": [s.to_dict() for s in self.slates],
            "players_by_slate": {sid: [p.to_dict() for p in players] for sid, players in self.players_by_slate.items()},
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "warnings": self.warnings,
        }
