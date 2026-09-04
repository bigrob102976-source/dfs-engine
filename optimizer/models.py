"""Typed data models for the lineup optimizer. Mirrors the rest of the
codebase's discipline: Optional fields stay Optional, nothing here
invents a projection, salary, or position -- it only rearranges data
that already exists on the unified DFS player pool (dfs/models.py).
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Set

from config.dk_roster_config import DK_CLASSIC_SALARY_CAP, DK_MAX_HITTERS_PER_TEAM, DK_MIN_GAMES_REPRESENTED
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
    # Multi-team stacks (M2): a SECOND, independent required team stack,
    # e.g. stack_size=5/stack_team="NYY" + stack_size_2=3/stack_team_2="BOS"
    # for a 5-3. Only ever meaningful together with stack_size/stack_team --
    # resolve_settings() (optimizer/constraints.py) rejects stack_size_2
    # set without an explicit stack_team (no AUTO primary-team selection
    # for two-team stacks) or without stack_team_2, and rejects
    # stack_team == stack_team_2. None/None (the default) is byte-identical
    # to every pre-M2 single-team-or-no-stack build.
    stack_size_2: Optional[int] = None
    stack_team_2: Optional[str] = None
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
    # M3 (Ops Finish): a real, documented DraftKings Classic MLB rule --
    # a legal lineup must include players from at least this many
    # different games. Previously defined (config/dk_roster_config.py)
    # and used only for a coarse POOL-level feasibility pre-check
    # (dfs/roster_feasibility.py -- "is a legal lineup theoretically
    # possible from this pool at all"), never enforced on the actual
    # PER-LINEUP the solver picks -- a pool spanning 5 games could still
    # have every one of its slots filled from a single game, which is a
    # real DK rule violation the system previously never caught. Always
    # on by default (this is a fixed rule, not a user preference, same
    # pattern as team_max_hitters/salary_cap above); settable only for
    # tests that want to exercise a pool with fewer real games than DK's
    # own minimum without every such test needing multi-game fixtures.
    min_games_represented: int = DK_MIN_GAMES_REPRESENTED
    # Milestone 10: all optional, all None/unused unless --ownership was supplied.
    max_total_ownership: Optional[float] = None
    max_player_ownership: Optional[float] = None
    min_player_ownership: Optional[float] = None
    # Milestone 14: optional minimum total lineup salary (a "spend floor"
    # symmetric to salary_cap's ceiling) and an optional override of the
    # solver's per-lineup CP-SAT time budget (see
    # config/optimizer_config.py::INTERACTIVE_SOLVER_MAX_TIME_SECONDS).
    # Both None by default -- unset means "no floor" / "use the batch
    # default (SOLVER_MAX_TIME_SECONDS)", identical to before this field existed.
    min_salary: Optional[int] = None
    time_limit_seconds: Optional[float] = None

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
    # Multi-team stacks (M2): the second team's own hitter count, only
    # ever set when the build requested a two-team stack (settings.stack_team_2)
    # -- None/0 for every no-stack or single-team-stack lineup, identical
    # to before this field existed.
    secondary_stack_team: Optional[str] = None
    secondary_stack_size: int = 0

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
            "secondary_stack_team": self.secondary_stack_team,
            "secondary_stack_size": self.secondary_stack_size,
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
