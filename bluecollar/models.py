"""Typed data models for the BlueCollar DFS integration (MLB DraftKings
endpoint). Mirrors the Optional-everywhere, never-invent-a-value
discipline of fantasypros/models.py and dfs/models.py.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class BlueCollarSlateMatch:
    """Result of matching one DraftKings provider slate to a BlueCollar
    slate (see bluecollar/slate_matcher.py). `status` is one of:
    "matched" | "ambiguous" | "no_bluecollar_slates" | "no_candidate" --
    never a silent guess."""

    status: str
    dk_slate_id: str
    bluecollar_slate_id: Optional[str] = None
    bluecollar_slate_name: Optional[str] = None
    reason: Optional[str] = None
    candidate_slate_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BlueCollarPlayerProjection:
    """One BlueCollar player, after MLB identity resolution
    (bluecollar/player_matcher.py) and zero-value handling
    (bluecollar/build.py). Every DK row this doesn't match is still
    recorded with match_status="unmatched"/"ambiguous" -- never silently
    dropped."""

    bluecollar_local_id: str  # locally derived (name+team+position) -- see external_projections/bluecollar_provider.py
    name: str
    team: str
    position: str
    opponent: Optional[str] = None
    salary: Optional[int] = None

    # None means BlueCollar reported no usable projection for this
    # player (a raw value <= 0, treated as NOT AVAILABLE rather than a
    # real zero-point projection -- see bluecollar/build.py's
    # module docstring). raw_projection preserves exactly what
    # BlueCollar returned, even when usable_projection is None, for
    # transparency/debugging -- never shown to a member as "the"
    # projection.
    raw_projection: Optional[float] = None
    usable_projection: Optional[float] = None

    match_status: str = "unmatched"  # "matched" | "unmatched" | "ambiguous"
    match_confidence: Optional[str] = None
    mlb_player_id: Optional[str] = None
    candidate_mlb_ids: List[str] = field(default_factory=list)
    candidate_names: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BlueCollarSnapshot:
    """The full persisted document -- one per (date, dk_slate_id,
    retrieved_at). Never contains the API key or any request header."""

    slate_date: str
    dk_slate_id: str
    bluecollar_slate_id: Optional[str]
    bluecollar_slate_name: Optional[str]
    bluecollar_updated: Optional[str]  # BlueCollar's own "updated" field, verbatim
    retrieved_at: str
    slate_match_status: str
    slate_match_reason: Optional[str]

    player_count: int
    matched_count: int
    usable_projection_count: int

    players: List[BlueCollarPlayerProjection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slate_date": self.slate_date,
            "dk_slate_id": self.dk_slate_id,
            "bluecollar_slate_id": self.bluecollar_slate_id,
            "bluecollar_slate_name": self.bluecollar_slate_name,
            "bluecollar_updated": self.bluecollar_updated,
            "retrieved_at": self.retrieved_at,
            "slate_match_status": self.slate_match_status,
            "slate_match_reason": self.slate_match_reason,
            "player_count": self.player_count,
            "matched_count": self.matched_count,
            "usable_projection_count": self.usable_projection_count,
            "players": [p.to_dict() for p in self.players],
        }
