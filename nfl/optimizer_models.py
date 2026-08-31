"""NFL M3/M4 -- typed data models for the NFL solver (roster-feasibility
and, as of M4, projection modes).

Deliberately NOT optimizer/models.py's OptimizerPlayer/Lineup -- those
require non-Optional projection/ceiling floats (every objective mode in
optimizer/objective.py reads them directly), which is structurally
incompatible with M3/M4's explicit "never invent a projection" rule.
NflOptimizerPlayer.projection stays Optional[float] = None -- a real
Big Money Native projection when NFL M4's provider has one for this
player, None otherwise. None is never treated as zero anywhere in
nfl/solver.py: projection mode EXCLUDES an unprojected player from
eligibility entirely rather than optimizing as though they'd score
nothing."""

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
    # NFL M4: None until Big Money Native has a real projection for this
    # player -- never 0.0 as a stand-in. See nfl/projection_merge.py for
    # how this gets populated from a NflProjectionRecord.
    projection: Optional[float] = None


@dataclass
class NflOptimizerSettings:
    # "roster_feasibility" (M3, unchanged) or "projection" (M4) -- see
    # nfl/solver.py::generate_lineups() for the objective each mode uses.
    mode: str = "roster_feasibility"
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
    # Explicit, unmissable label of which objective built this lineup:
    # "roster_feasibility" (M3 -- maximize deterministic salary
    # utilization, never a fantasy-points recommendation) or
    # "projection" (M4 -- maximize real Big Money Native projections
    # only). Always set explicitly by nfl/solver.py from the settings
    # that produced this lineup -- never left at a stale default.
    mode: str = "roster_feasibility"
    # NFL M4: sum of each assigned player's real projection, only when
    # mode == "projection" (None in roster_feasibility mode -- there is
    # no projection basis to sum, and 0.0 would misleadingly imply one).
    total_projection: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "assignments": [a.to_dict() for a in self.assignments],
            "total_salary": self.total_salary,
            "remaining_salary": self.remaining_salary,
            "total_projection": self.total_projection,
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
