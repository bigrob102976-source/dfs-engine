"""Typed data models for the ownership model. Mirrors the rest of the
codebase's discipline: Optional fields stay Optional, and
`projected_ownership`/`ownership_confidence` are named exactly that --
never `actual_ownership` or `field_ownership` -- because they are a
model prediction, not observed contest data.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class OwnershipInputPlayer:
    """One ACTIVE player read directly from a saved DK player pool
    (dfs_input/.../dk_player_pool_*.json), reduced to what the ownership
    feature builder needs. Built independently of optimizer.models.OptimizerPlayer
    so ownership/ has no dependency on optimizer/ internals."""

    dk_player_id: str
    mlb_player_id: Optional[str]
    name: str
    team: str
    opponent: Optional[str]
    game_id: Optional[str]
    player_type: str  # "pitcher" | "hitter"
    dk_positions: List[str]
    salary: int
    projection: float
    ceiling: float
    overall_score: Optional[float]
    risk_score: Optional[float]
    confidence: Optional[float]
    batting_order: Optional[int]
    season_sample_size: Optional[float]
    tags: List[str] = field(default_factory=list)


@dataclass
class TeamPopularity:
    """Aggregate, slate-relative popularity of one team's offense. This
    is NOT a Vegas/implied-total model -- see ownership/features.py."""

    team: str
    team_popularity_score: float  # 0-100, slate-relative
    aggregate_projection: float
    top5_projection: float
    hitter_count: int
    aggregate_projected_ownership: float = 0.0  # filled in after ownership is computed

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OwnershipProjection:
    """Output of the ownership model for a single player. `projected_ownership`
    and `ownership_confidence` are always MODEL predictions -- see module docstring."""

    dk_player_id: str
    mlb_player_id: Optional[str]
    name: str
    team: str
    opponent: Optional[str]
    player_type: str
    dk_positions: List[str]
    salary: int

    projection: float
    ceiling: float
    overall_score: Optional[float]
    risk_score: Optional[float]
    confidence: Optional[float]

    projected_ownership: float
    ownership_confidence: float

    chalk_score: float
    leverage_score: float
    ownership_tier: str

    batting_order: Optional[int] = None
    feature_breakdown: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    model_version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
