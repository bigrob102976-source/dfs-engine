"""Typed output models for the Native Projection Model (native_projections/).

Every statistical field is Optional/defaulted: this package must tolerate
missing upstream data without inventing values (same discipline as
models/pitcher.py, models/batter.py, projection_engine/models.py).

The defining difference from the existing Independent Projection
(agents/pitcher_agent.py, agents/batter_agent.py) is that EVERY component
that goes into the final DK-points number is preserved here, not just the
final projection/ceiling/floor -- see ComponentValue.
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class HitterOpportunity:
    """Expected plate-appearance opportunity for a hitter -- see
    native_projections/playing_time.py."""

    expected_pa: float
    pa_confidence: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PitcherOpportunity:
    """Expected workload opportunity for a pitcher -- see
    native_projections/playing_time.py."""

    expected_innings: float
    expected_batters_faced: float
    expected_pitch_count: float
    workload_confidence: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComponentValue:
    """One projected baseball-outcome component, fully explainable: the
    expected COUNT of that event, the DK point value of a single event,
    and the resulting point contribution (expected_count * dk_points_per_event).
    `reason` is optional context (e.g. "regressed toward league avg: 10 PA
    sample"). Used for every hitter/pitcher outcome component -- see
    dk_scoring.py."""

    expected_count: float
    dk_points_per_event: float
    dk_points: float
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HitterComponents:
    singles: ComponentValue
    doubles: ComponentValue
    triples: ComponentValue
    home_runs: ComponentValue
    walks: ComponentValue
    hit_by_pitch: ComponentValue
    stolen_bases: ComponentValue
    runs: ComponentValue
    rbi: ComponentValue
    # Informational only -- DraftKings Classic does not score hitter
    # strikeouts at all, so this is never a ComponentValue (no DK point
    # value exists for it); kept for transparency/validation only.
    strikeouts_expected: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PitcherComponents:
    innings_pitched: ComponentValue
    strikeouts: ComponentValue
    walks: ComponentValue
    hit_batsmen: ComponentValue
    hits_allowed: ComponentValue
    earned_runs: ComponentValue
    # Informational only -- never baked into native_projection points (DK's
    # win bonus is postgame-only; see config/scoring_config.py's own
    # documented reasoning for excluding win probability from the pregame
    # formula, which this model follows). None when no Vegas moneyline is
    # available at all; win_probability_is_mock=True flags a synthetic
    # (mock-provider) source rather than a real market price.
    win_probability: Optional[float] = None
    win_probability_is_mock: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InputCoverage:
    """How much of a player's OPTIONAL input data was actually available
    vs. defaulted/missing -- feeds both `reasons` and confidence (see
    native_projections/uncertainty.py)."""

    fields_available: int
    fields_total: int
    missing_fields: List[str] = field(default_factory=list)

    @property
    def fraction(self) -> float:
        return self.fields_available / self.fields_total if self.fields_total else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["fraction"] = round(self.fraction, 3)
        return d


@dataclass
class NativePlayerProjection:
    """The Native Projection Model's full, explainable output for one
    player."""

    player_id: str
    name: str
    team: str
    player_type: str  # "pitcher" | "hitter"
    opponent: Optional[str] = None
    game_id: Optional[str] = None
    salary: Optional[int] = None
    positions: List[str] = field(default_factory=list)
    batting_order: Optional[int] = None

    native_projection: float = 0.0
    native_ceiling: float = 0.0
    native_floor: float = 0.0
    confidence: float = 0.0
    variance: float = 0.0

    model_version: str = ""

    hitter_opportunity: Optional[HitterOpportunity] = None
    pitcher_opportunity: Optional[PitcherOpportunity] = None
    hitter_components: Optional[HitterComponents] = None
    pitcher_components: Optional[PitcherComponents] = None

    input_coverage: Optional[InputCoverage] = None
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    generated_at: str = ""
    source_pitcher_snapshot_path: Optional[str] = None
    source_batter_snapshot_path: Optional[str] = None
    source_environment_snapshot_path: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict() serializes InputCoverage's real fields but not its
        # `fraction` @property -- patch it back in via to_dict() explicitly,
        # same pattern projection_engine/models.py uses for its own
        # non-plain-dataclass nested field (`signals`).
        if self.input_coverage is not None:
            d["input_coverage"] = self.input_coverage.to_dict()
        return d


@dataclass
class NativeProjectionDocument:
    """Slate-level wrapper -- mirrors research/prediction_snapshot.py's
    document shape (slate_date/generated_at/model_version/source paths/
    player list), adapted for a single unified pitcher+hitter document."""

    slate_date: str
    generated_at: str
    model_version: str
    pitcher_snapshot_path: Optional[str]
    batter_snapshot_path: Optional[str]
    environment_snapshot_path: Optional[str]
    player_count: int
    players: List[NativePlayerProjection]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slate_date": self.slate_date,
            "generated_at": self.generated_at,
            "model_version": self.model_version,
            "pitcher_snapshot_path": self.pitcher_snapshot_path,
            "batter_snapshot_path": self.batter_snapshot_path,
            "environment_snapshot_path": self.environment_snapshot_path,
            "player_count": self.player_count,
            "players": [p.to_dict() for p in self.players],
            "warnings": list(self.warnings),
        }
