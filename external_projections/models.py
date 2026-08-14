"""Typed data shapes for the external projection provider framework
(Milestone 17). Mirrors dfs/providers/models.py's normalized-provider-
output discipline: nothing downstream of external_projections/ (the
adjustment engine, the merge step, the dashboard) should ever need to
know which concrete provider supplied a projection.

Every optional field defaults to/stays None when a provider doesn't
supply it -- never invented.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class ExternalSlateInfo:
    """One DFS slate an external projection provider knows about for a
    given date (provider-agnostic, same shape as dfs/providers'
    ProviderSlateInfo but intentionally a separate type -- a projection
    provider and a salary provider are different concerns even when the
    same company happens to offer both)."""

    slate_id: str
    slate_name: Optional[str]
    sport: str
    site: str
    player_count: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExternalProjectionPlayer:
    """One player's projection as reported by an external provider for
    one slate. This module never adjusts or interprets these values --
    see external_projections/adjustment_engine.py for that."""

    external_player_id: str
    name: str
    team: str
    position: str
    projection: float
    provider_name: str
    updated_at: str
    slate_id: str

    opponent: Optional[str] = None
    salary: Optional[int] = None
    ceiling: Optional[float] = None
    floor: Optional[float] = None
    ownership_projection: Optional[float] = None
    slate_name: Optional[str] = None
    provider_version: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AdjustmentFactor:
    """One signal the Big Money Adjustment Engine used to move a
    player's projection away from the external baseline. `delta` is a
    raw fantasy-point movement (already capped -- see
    external_projections/adjustment_engine.py); `confidence` echoes the
    research confidence (0-100) available at the time this factor fired."""

    factor: str
    delta: float
    reason: str
    confidence: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlayerProjectionRecord:
    """The full three-way projection record for one player: everything
    the dashboard's PROJECTION COMPARISON view and the optimizer's
    Projection Source selector need. `independent_player_id` is our own
    canonical MLB player_id (the same id predictions/pitcher_board and
    batter_board snapshots use) -- the join key between this record and
    the rest of the pipeline (DK pool, ownership). Never None once a
    match has been made; projection_merge.py never creates a record for
    an unmatched external player.

    Independent and external values are NEVER mutated after being
    copied in here -- only adjusted_* fields are engine output."""

    independent_player_id: str
    name: str
    team: str
    player_type: str  # "pitcher" | "hitter"

    external_player_id: Optional[str] = None
    external_projection: Optional[float] = None
    external_ceiling: Optional[float] = None
    external_floor: Optional[float] = None
    external_provider: Optional[str] = None
    external_provider_timestamp: Optional[str] = None

    independent_projection: Optional[float] = None
    independent_ceiling: Optional[float] = None
    independent_floor: Optional[float] = None

    adjusted_projection: Optional[float] = None
    adjusted_ceiling: Optional[float] = None
    adjusted_floor: Optional[float] = None

    adjustment_delta: Optional[float] = None
    adjustment_percent: Optional[float] = None
    adjustment_confidence: Optional[float] = None
    adjustment_reasons: List[str] = field(default_factory=list)
    adjustments: List[AdjustmentFactor] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["adjustments"] = [a.to_dict() for a in self.adjustments]
        return d


@dataclass
class ProjectionMergeResult:
    """Output of projection_merge.merge_projections: the matched
    records plus an honest account of what DIDN'T match, so a caller
    (script/dashboard) can surface it rather than silently dropping
    players."""

    records: List[PlayerProjectionRecord]
    unmatched_external: List[str] = field(default_factory=list)  # external player names
    unmatched_independent: List[str] = field(default_factory=list)  # our own player names
    ambiguous_external: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "records": [r.to_dict() for r in self.records],
            "unmatched_external": self.unmatched_external,
            "unmatched_independent": self.unmatched_independent,
            "ambiguous_external": self.ambiguous_external,
        }
