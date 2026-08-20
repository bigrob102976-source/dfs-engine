"""Typed data models for FantasyPros MLB daily projections. Mirrors the
Optional-everywhere, never-invent-a-value discipline of dfs/models.py.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class FantasyProsRawPlayer:
    """One player record as FantasyPros' /mlb/{season}/projections endpoint
    actually returns it (confirmed via live API calls, 2026-08-19 --
    fields are NOT assumed from documentation). `stats` holds every raw
    projected-stat field from the response verbatim (e.g. "1b", "hrs",
    "ip", "k") so a future stat FantasyPros adds is preserved even before
    fantasypros/scoring.py is updated to use it."""

    fpid: str
    player_id: str
    name: str
    team_id: str
    player_type: str  # "pitcher" | "hitter" -- known from which endpoint (position=H/P) returned this record, not guessed
    yahoo_id: Optional[str] = None
    stats: Dict[str, float] = field(default_factory=dict)


@dataclass
class FantasyProsPlayerProjection:
    """One FantasyPros player, after DK-points conversion (fantasypros/scoring.py)
    and MLB identity resolution (fantasypros/matcher.py). Every DK row this
    doesn't match is still recorded here with match_status="unmatched"/"ambiguous"
    -- never silently dropped, mirroring dfs/models.py::PlayerMatch's own
    "never guess" discipline."""

    fantasypros_id: str
    name: str
    team: str
    player_type: str

    yahoo_id: Optional[str] = None
    raw_stats: Dict[str, float] = field(default_factory=dict)

    dk_points: Optional[float] = None
    dk_points_breakdown: Dict[str, float] = field(default_factory=dict)

    match_status: str = "unmatched"  # "matched" | "unmatched" | "ambiguous"
    match_confidence: Optional[str] = None
    mlb_player_id: Optional[str] = None
    candidate_mlb_ids: List[str] = field(default_factory=list)
    candidate_names: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FantasyProsSnapshot:
    """The full persisted document -- one per (date, retrieved_at). Never
    contains the API key or any request header (see fantasypros/client.py's
    module docstring)."""

    slate_date: str
    retrieved_at: str
    hitter_count: int
    pitcher_count: int
    hitters_matched: int
    pitchers_matched: int
    public_api_limited: bool
    api_tier: Optional[str]
    players: List[FantasyProsPlayerProjection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slate_date": self.slate_date,
            "retrieved_at": self.retrieved_at,
            "hitter_count": self.hitter_count,
            "pitcher_count": self.pitcher_count,
            "hitters_matched": self.hitters_matched,
            "pitchers_matched": self.pitchers_matched,
            "public_api_limited": self.public_api_limited,
            "api_tier": self.api_tier,
            "players": [p.to_dict() for p in self.players],
        }
