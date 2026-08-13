"""Typed data models for the lineup optimizer. Mirrors the rest of the
codebase's discipline: Optional fields stay Optional, nothing here
invents a projection, salary, or position -- it only rearranges data
that already exists on the unified DFS player pool (dfs/models.py).
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set

from config.dk_roster_config import DK_CLASSIC_SALARY_CAP, DK_MAX_HITTERS_PER_TEAM
from config.optimizer_config import ALLOW_PITCHER_VS_HITTER_DEFAULT, DEFAULT_MAX_EXPOSURE, DEFAULT_MIN_UNIQUE


@dataclass
class OptimizerPlayer:
    """One ACTIVE player from a saved DFS player pool, reduced to only
    what the optimizer needs. `key` is what locks/excludes/exposure are
    tracked by -- always the DraftKings player ID (stable and unique
    within one pool, unlike name)."""

    key: str  # dk_player_id
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
    floor: Optional[float]
    risk_score: Optional[float]
    confidence: Optional[float]
    season_sample_size: Optional[float]
    # Milestone 10: optional ownership-model fields, merged in from a
    # separately-loaded ownership snapshot (--ownership). Always None
    # unless that flag was passed -- every existing objective mode and
    # constraint that doesn't reference these fields behaves identically
    # whether or not ownership data was supplied.
    projected_ownership: Optional[float] = None
    leverage_score: Optional[float] = None
    ownership_confidence: Optional[float] = None


@dataclass
class OptimizerSettings:
    objective_mode: str = "projection"  # projection | ceiling | balanced
    num_lineups: int = 1
    min_unique: int = DEFAULT_MIN_UNIQUE
    stack_size: Optional[int] = None
    stack_team: Optional[str] = None
    locks: List[str] = field(default_factory=list)          # player names, as given on the CLI
    excludes: List[str] = field(default_factory=list)
    max_exposure: Dict[str, float] = field(default_factory=dict)   # player name -> fraction
    max_exposure_default: float = DEFAULT_MAX_EXPOSURE
    min_exposure: Dict[str, float] = field(default_factory=dict)   # player name -> fraction
    min_confidence: Optional[float] = None
    min_season_pa: Optional[float] = None
    max_player_risk: Optional[float] = None
    allow_pitcher_vs_hitter: bool = ALLOW_PITCHER_VS_HITTER_DEFAULT
    salary_cap: int = DK_CLASSIC_SALARY_CAP
    team_max_hitters: int = DK_MAX_HITTERS_PER_TEAM
    # Milestone 10: all optional, all None/unused unless --ownership was supplied.
    max_total_ownership: Optional[float] = None
    max_player_ownership: Optional[float] = None
    min_player_ownership: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LineupPlayerAssignment:
    slot: str  # "P" | "C" | "1B" | "2B" | "3B" | "SS" | "OF"
    dk_player_id: str
    mlb_player_id: Optional[str]
    name: str
    team: str
    opponent: Optional[str]
    salary: int
    projection: float
    ceiling: float
    floor: Optional[float]
    risk_score: Optional[float]
    confidence: Optional[float]
    projected_ownership: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Lineup:
    index: int
    assignments: List[LineupPlayerAssignment]
    salary: int
    remaining_salary: int
    projection: float
    ceiling: float
    floor: float
    average_risk: Optional[float]
    average_confidence: Optional[float]
    team_counts: Dict[str, int]
    primary_stack_team: Optional[str]
    primary_stack_size: int
    # Milestone 10: None unless ownership data was supplied when the lineup was built.
    sum_ownership: Optional[float] = None
    average_ownership: Optional[float] = None
    max_ownership: Optional[float] = None
    players_above_chalk_threshold: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "assignments": [a.to_dict() for a in self.assignments],
            "salary": self.salary,
            "remaining_salary": self.remaining_salary,
            "projection": self.projection,
            "ceiling": self.ceiling,
            "floor": self.floor,
            "average_risk": self.average_risk,
            "average_confidence": self.average_confidence,
            "team_counts": self.team_counts,
            "primary_stack_team": self.primary_stack_team,
            "primary_stack_size": self.primary_stack_size,
            "sum_ownership": self.sum_ownership,
            "average_ownership": self.average_ownership,
            "max_ownership": self.max_ownership,
            "players_above_chalk_threshold": self.players_above_chalk_threshold,
        }

    def player_keys(self) -> List[str]:
        return [a.dk_player_id for a in self.assignments]


@dataclass
class GenerationResult:
    lineups: List[Lineup]
    requested: int
    generated: int
    stopped_reason: Optional[str] = None  # set when generated < requested


@dataclass
class GenerationOutput:
    """Everything the CLI/validator/persistence layer needs, bundled so
    lineup_generator.generate_lineups() has one return value instead of
    a long positional tuple."""

    result: GenerationResult
    players_by_key: Dict[str, OptimizerPlayer]
    locked_keys: List[str]
    excluded_keys: Set[str]
    exposure_caps: Dict[str, int]
    min_exposure_targets: Dict[str, int]
