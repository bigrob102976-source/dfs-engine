"""Typed output models for the AI Projection Engine.

Every statistical field is Optional: the engine must tolerate missing
upstream signals without inventing values (same discipline as
models/pitcher.py, models/batter.py, ownership/models.py).
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class RawSignal:
    """One signal category's UN-weighted contribution, as computed
    directly from already-persisted upstream fields by signals.py.
    weights.py turns this into a weight-applied SignalContribution --
    kept separate so every configurable weight lives in exactly one
    place (config/projection_engine_config.py) rather than being baked
    into the signal-detection logic itself."""

    category: str
    label: str
    raw_delta: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SignalContribution:
    """One signal category's contribution to a single player's AI
    Projection. `delta` is already weight-applied (what actually moved
    the projection); `raw_delta` is the pre-weight value signals.py
    computed, kept for transparency/debugging in the Player Detail view."""

    category: str        # "weather" | "vegas" | "bullpen" | "park" | "ownership" | "matchup" | "recent_form" | "external"
    label: str            # display label, e.g. "Weather"
    raw_delta: float
    weight: float
    delta: float           # raw_delta * weight (+ any role-specific dampening)
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AIPlayerProjection:
    """The AI Projection Engine's full output for one player: the four
    projection tiers side by side (independent/external/adjusted/ai),
    every signal that moved the AI number, and the deterministic reasons
    behind them."""

    player_id: str
    name: str
    team: str
    player_type: str  # "pitcher" | "hitter"
    opponent: Optional[str] = None
    game_id: Optional[str] = None
    salary: Optional[int] = None

    independent_projection: Optional[float] = None
    independent_ceiling: Optional[float] = None
    independent_floor: Optional[float] = None
    external_projection: Optional[float] = None
    adjusted_projection: Optional[float] = None

    ai_projection: Optional[float] = None
    ai_ceiling: Optional[float] = None
    ai_floor: Optional[float] = None
    ai_confidence: Optional[float] = None
    ai_risk: Optional[float] = None
    ai_grade: Optional[str] = None
    ai_value_score: Optional[float] = None

    total_adjustment: float = 0.0
    total_adjustment_percent: Optional[float] = None
    adjustment_capped: bool = False

    signals: List[SignalContribution] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    ai_summary: str = ""

    model_version: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signals"] = [s.to_dict() for s in self.signals]
        return d
