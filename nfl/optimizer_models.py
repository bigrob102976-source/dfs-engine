"""NFL M3 -- typed data models for the NFL roster-feasibility solver.

Deliberately NOT optimizer/models.py's OptimizerPlayer/Lineup -- those
require non-Optional projection/ceiling floats (every objective mode in
optimizer/objective.py reads them directly), which is structurally
incompatible with M3's explicit "no real NFL projections yet, prove
roster feasibility only" scope. These models carry no projection field
at all -- there is nothing to invent or leave null.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_SALARY_CAP


@dataclass
class NflOptimizerPlayer:
    """One canonical NflPlayer (nfl/models.py), reduced to only what the
    roster-feasibility solver needs. `key` is DraftKings' own stable
    player_id -- what locks/excludes are tracked by."""

    key: str  # draftkings_player_id
    name: str
    team: str
    opponent: Optional[str]
    game_id: str
    position: str  # QB | RB | WR | TE | DST
    roster_slots: List[str]  # e.g. ["RB", "FLEX"] -- real DK eligibility, never re-derived
    salary: int
    is_team_entity: bool
    draft_group_id: int
    slate_date: str


@dataclass
class NflOptimizerSettings:
    num_lineups: int = 1
    min_unique: int = 1
    locks: List[str] = field(default_factory=list)  # player keys (draftkings_player_id)
    excludes: List[str] = field(default_factory=list)
    salary_cap: int = DK_NFL_CLASSIC_SALARY_CAP
    time_limit_seconds: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflLineupSlotAssignment:
    slot: str  # "QB" | "RB1" | "RB2" | "WR1" | "WR2" | "WR3" | "TE" | "FLEX" | "DST"
    draftkings_player_id: str
    name: str
    position: str
    team: str
    salary: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflLineup:
    index: int
    assignments: List[NflLineupSlotAssignment]
    total_salary: int
    remaining_salary: int
    draft_group_id: int
    slate_date: str
    sport: str = "NFL"
    # Explicit, unmissable label: this lineup was built to prove legal
    # roster construction only (maximize deterministic salary
    # utilization) -- never a fantasy-points recommendation. No
    # projection/ceiling field exists anywhere on this dataclass.
    mode: str = "roster_feasibility"

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "assignments": [a.to_dict() for a in self.assignments],
            "total_salary": self.total_salary,
            "remaining_salary": self.remaining_salary,
            "draft_group_id": self.draft_group_id,
            "slate_date": self.slate_date,
            "sport": self.sport,
            "mode": self.mode,
        }

    def player_keys(self) -> List[str]:
        return [a.draftkings_player_id for a in self.assignments]


@dataclass
class NflGenerationResult:
    lineups: List[NflLineup]
    requested: int
    generated: int
    stopped_reason: Optional[str] = None  # set when generated < requested
