"""NFL M12 -- the canonical Big Money Native NFL ownership record.

Deliberately NOT ownership/models.py::OwnershipProjection -- that
dataclass's `player_type: "pitcher"|"hitter"` split and MLB-only fields
(batting_order, mlb_player_id) don't apply to NFL's QB/RB/WR/TE/DST
position set or its shared FLEX slot (see NFL M12's Phase 0 audit).
This is a fresh, NFL-native record mirroring nfl/projection_models.py's
own conventions: real DraftKings identity only, Optional-everywhere,
percentages are always 0-100 floats (never 0-1), and a player with no
usable projection gets ownership_projection = None -- never 0.0, which
would misleadingly claim "definitely unowned" instead of honestly
"no basis to estimate this player's ownership at all".
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

NFL_OWNERSHIP_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "DST"})


@dataclass
class NflOwnershipInputPlayer:
    """One player with a usable projection, reduced to exactly what
    nfl/ownership_features.py and nfl/ownership_model.py need. Built by
    the caller (nfl/ownership_model.py::build_nfl_ownership_projections)
    from the canonical pool + a projection record + usage/game-context
    data that's already been resolved -- this dataclass itself makes no
    identity-matching or data-source decisions.

    usage_share is a single pre-blended 0-1 (or None) value -- WHICH
    underlying stat(s) it represents differs by position (RB: carry+
    target share; WR/TE: target+reception share; QB/DST: always None,
    no usage-share concept applies) -- see nfl/ownership_model.py's
    _usage_share_for_player() for that position-specific selection.
    team_implied_total/opponent_implied_total are both None whenever
    Vegas isn't configured (nullable by design -- never fabricated)."""

    draftkings_player_id: str
    name: str
    position: str  # QB | RB | WR | TE | DST
    team: str
    opponent: Optional[str]
    salary: int
    projection: float  # always real -- callers exclude players with projection is None before constructing this
    ceiling: Optional[float]
    usage_share: Optional[float] = None
    team_implied_total: Optional[float] = None
    opponent_implied_total: Optional[float] = None


@dataclass
class NflOwnershipRecord:
    """One player's Big Money Native ownership estimate for one NFL
    DraftGroup. Every identity field is DraftKings' own real data (see
    nfl/models.py::NflPlayer) -- this record never invents an identity,
    only attaches an ownership estimate to one that already exists in
    the canonical pool. Joined downstream by draftkings_player_id ONLY
    -- never by name (see nfl/ownership_merge.py)."""

    sport: str  # "NFL"
    draft_group_id: int
    slate_date: str

    draftkings_player_id: str
    canonical_player_id: str  # == draftkings_player_id -- kept as its own field to mirror NflProjectionRecord's join-key naming
    name: str
    position: str  # QB | RB | WR | TE | DST
    team: str
    opponent: Optional[str]

    # None when the player has no usable Big Money Native projection to
    # estimate ownership FROM -- never 0.0 as a stand-in. See
    # nfl/ownership_model.py's module docstring.
    ownership_projection: Optional[float]
    ownership_rank: Optional[int]  # 1 = most-owned player on the slate; None alongside ownership_projection

    source: str
    source_provenance: str
    method: str  # "deterministic_estimator" (NFL M12) -- never implies a trained ML model when it isn't one
    model_version: str
    generated_at: str

    # Diagnostics -- never authoritative on their own, carried alongside
    # the estimate so a consumer can see WHY without re-deriving it.
    salary: Optional[int] = None
    projection: Optional[float] = None
    ceiling: Optional[float] = None
    value: Optional[float] = None  # projection / salary * config.VALUE_NORMALIZATION_CONSTANT
    ownership_tier: Optional[str] = None
    chalk_score: Optional[float] = None
    leverage_score: Optional[float] = None
    ownership_confidence: Optional[float] = None
    flex_ownership_component: Optional[float] = None  # RB/WR/TE only -- the slice of ownership_projection attributable to shared FLEX demand
    feature_breakdown: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflOwnershipValidationFinding:
    level: str  # "BLOCK" | "WARN"
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflOwnershipValidationResult:
    passed: bool
    findings: List[NflOwnershipValidationFinding] = field(default_factory=list)

    total_pool_players: int = 0
    players_with_ownership: int = 0
    players_missing_ownership: int = 0

    ownership_sum_by_position: Dict[str, float] = field(default_factory=dict)
    ownership_expected_by_position: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
            "total_pool_players": self.total_pool_players,
            "players_with_ownership": self.players_with_ownership,
            "players_missing_ownership": self.players_missing_ownership,
            "ownership_sum_by_position": self.ownership_sum_by_position,
            "ownership_expected_by_position": self.ownership_expected_by_position,
        }


@dataclass
class NflOwnershipSnapshot:
    """Everything needed to persist and reproduce one Big Money Native
    NFL ownership run for one DraftGroup."""

    sport: str
    draft_group_id: int
    slate_date: str
    source: str
    source_provenance: str
    method: str
    model_version: str
    generated_at: str
    records: List[NflOwnershipRecord]
    validation: NflOwnershipValidationResult
    normalization_report: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sport": self.sport,
            "draft_group_id": self.draft_group_id,
            "slate_date": self.slate_date,
            "source": self.source,
            "source_provenance": self.source_provenance,
            "method": self.method,
            "model_version": self.model_version,
            "generated_at": self.generated_at,
            "records": [r.to_dict() for r in self.records],
            "validation": self.validation.to_dict(),
            "normalization_report": self.normalization_report,
        }
