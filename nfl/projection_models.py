"""NFL M4 -- the canonical Big Money Native NFL projection record.

Deliberately NOT external_projections/models.py::PlayerProjectionRecord
-- that dataclass is MLB's three-way (external/independent/adjusted)
comparison record, tied to player_type: "pitcher"|"hitter" and MLB's
own independent_player_id. This is a fresh, first-party record: Big
Money DFS's own NFL projections are the customer-facing path (see this
milestone's product decision), not a comparison against a third party.

NULL != 0: projection/floor/ceiling all stay None until a real model
has actually produced a value. Nothing here ever invents a number to
satisfy a downstream consumer -- a caller with no real projection sees
None and must decide what that means (see nfl/solver.py's projection
mode, which excludes such a player from projection-based optimization
entirely rather than treating None as zero).
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

# First-party provenance -- not "unofficial" (draftkings_unofficial/)
# and not "external" (external_projections/): this is Big Money DFS's
# own model output. Mirrors dfs/providers/source_provenance.py's
# naming convention for a new, distinct provenance value.
BIG_MONEY_NATIVE = "BIG_MONEY_NATIVE"

NFL_PROJECTION_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "DST"})


@dataclass
class NflProjectionRecord:
    """One player's Big Money Native projection for one NFL DraftGroup.
    Every identity field here is DraftKings' own real data (see
    nfl/models.py::NflPlayer, nfl/pool_builder.py) -- this record never
    invents an identity, only attaches a projection to one that already
    exists in the canonical pool."""

    sport: str  # "NFL"
    draft_group_id: int

    canonical_player_id: str  # == NflPlayer.draftkings_player_id (M4's only identity join key -- see nfl/projection_merge.py)
    draftkings_player_id: str
    draftable_ids: List[str]  # mirrors NflPlayer.draftable_ids

    name: str
    position: str  # QB | RB | WR | TE | DST
    team: str
    opponent: Optional[str]

    projection: Optional[float]  # None until a real model has scored this player -- never 0.0 as a stand-in
    floor: Optional[float] = None
    ceiling: Optional[float] = None

    source: str = BIG_MONEY_NATIVE
    source_provenance: str = BIG_MONEY_NATIVE

    model_name: Optional[str] = None
    model_version: Optional[str] = None

    generated_at: Optional[str] = None  # when THIS projection was produced
    data_timestamp: Optional[str] = None  # when the underlying input data was as-of
    feature_version: Optional[str] = None
    is_stale: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflProjectionValidationFinding:
    level: str  # "BLOCK" | "WARN"
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflProjectionValidationResult:
    passed: bool
    findings: List[NflProjectionValidationFinding] = field(default_factory=list)

    total_pool_players: int = 0
    projected_players: int = 0
    missing_players: int = 0
    match_rate: Optional[float] = None
    position_projected_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
            "total_pool_players": self.total_pool_players,
            "projected_players": self.projected_players,
            "missing_players": self.missing_players,
            "match_rate": self.match_rate,
            "position_projected_counts": self.position_projected_counts,
        }


@dataclass
class NflProjectionSnapshot:
    """Everything needed to persist and reproduce one Big Money Native
    projection run for one DraftGroup."""

    sport: str
    draft_group_id: int
    slate_date: str
    source: str
    source_provenance: str
    generated_at: str
    model_name: Optional[str]
    model_version: Optional[str]
    records: List[NflProjectionRecord]
    validation: NflProjectionValidationResult

    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "draft_group_id": self.draft_group_id,
            "slate_date": self.slate_date,
            "source": self.source,
            "source_provenance": self.source_provenance,
            "generated_at": self.generated_at,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "records": [r.to_dict() for r in self.records],
            "validation": self.validation.to_dict(),
        }
