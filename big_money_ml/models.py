"""Milestone 32.2B -- typed output models for Big Money ML shadow
inference. Mirrors native_projections/models.py's discipline: every
field Optional/defaulted, nothing invented for missing upstream data.
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional

LIVE_PREGAME = "LIVE_PREGAME"
PREGAME_FROZEN = "PREGAME_FROZEN"
MISSING = "MISSING"
INVALID_FEATURE_PARITY = "INVALID_FEATURE_PARITY"


@dataclass
class MLPitcherProjection:
    player_id: str  # mlb_player_id -- the authoritative join key, never name-only
    dk_player_id: Optional[str]
    name: str
    team: str
    opponent: str
    game_id: Optional[str]
    salary: Optional[int]

    projection: Optional[float]
    model_version: str
    data_quality_score: Optional[float]
    feature_coverage: Optional[float]
    missing_features: List[str] = field(default_factory=list)

    projection_status: str = MISSING
    feature_timestamp: Optional[str] = None
    game_scheduled_start_utc: Optional[str] = None

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MLProjectionDocument:
    slate_date: str
    generated_at: str
    model_version: str
    warehouse_version: str

    raw_dk_pitcher_count: int
    starting_pitcher_count: int
    ml_eligible_pitcher_count: int
    ml_projections_generated: int
    ml_projections_missing: int

    feature_parity_summary: dict
    players: List[MLPitcherProjection] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slate_date": self.slate_date,
            "generated_at": self.generated_at,
            "model_version": self.model_version,
            "warehouse_version": self.warehouse_version,
            "raw_dk_pitcher_count": self.raw_dk_pitcher_count,
            "starting_pitcher_count": self.starting_pitcher_count,
            "ml_eligible_pitcher_count": self.ml_eligible_pitcher_count,
            "ml_projections_generated": self.ml_projections_generated,
            "ml_projections_missing": self.ml_projections_missing,
            "feature_parity_summary": self.feature_parity_summary,
            "players": [p.to_dict() for p in self.players],
            "warnings": list(self.warnings),
        }
