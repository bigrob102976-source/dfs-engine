"""NFL M3/M4/M13 -- typed data models for the NFL solver (roster-
feasibility, projection/ceiling/leverage objective modes, and, as of
M13, tournament lineup-construction controls: QB stacking, bring-back,
RB+DST correlation, team/game limits, and player exposure).

Deliberately NOT optimizer/models.py's OptimizerPlayer/Lineup -- those
require non-Optional projection/ceiling floats (every objective mode in
optimizer/objective.py reads them directly), which is structurally
incompatible with this project's explicit "never invent a projection"
rule. NflOptimizerPlayer.projection/ceiling/leverage_score all stay
Optional[float] = None -- real Big Money Native/ownership values when
available, None otherwise. None is never treated as zero anywhere in
nfl/solver.py: each scoring objective mode EXCLUDES a player missing
the data it needs from eligibility entirely rather than optimizing as
though they'd score nothing (see nfl/objective.py)."""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_SALARY_CAP
from config.nfl_optimizer_config import DEFAULT_MAX_EXPOSURE


@dataclass
class NflOptimizerPlayer:
    """One canonical NflPlayer (nfl/models.py), reduced to only what the
    solver needs. `key` is DraftKings' own stable player_id -- what
    locks/excludes/exposure are tracked by."""

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
    # NFL M13: None until Big Money Native has a real ceiling for this
    # player -- required (alongside projection) for "ceiling"/"leverage"
    # objective modes; never substituted with projection (see
    # nfl/objective.py's module docstring).
    ceiling: Optional[float] = None
    # NFL M12: None until Big Money Native has a real ownership estimate
    # for this player -- never 0.0 as a stand-in (see nfl/ownership_
    # model.py). Display/decision-support data; also feeds "leverage"
    # mode's small capped nudge (NFL M13, see nfl/objective.py).
    projected_ownership: Optional[float] = None
    # NFL M13: the ownership model's own leverage_score (quality
    # percentile minus ownership percentile, roughly [-100, 100]) --
    # None whenever ownership wasn't computed for this player. Only
    # "leverage" objective mode reads this; every other mode ignores it.
    leverage_score: Optional[float] = None
    # NFL M14: DraftKings' own real raw status string ("None"/"Q"/"OUT"/
    # "IR"/etc., verbatim from NflPlayer.status) -- None means the field
    # itself was never populated (treated as ACTIVE by nfl/status.py,
    # same as a real "None"). Used for status-based exclusion (see
    # nfl/status.py) and UI display; never fabricated.
    raw_status: Optional[str] = None
    # NFL M14: real ISO-8601 UTC game start time (verbatim from
    # NflPlayer.game_start_time) -- used for late-swap lock-state
    # computation (nfl/game_lock.py). None only when DK itself hasn't
    # published a start time yet.
    game_start_time: Optional[str] = None


@dataclass
class NflStackConfig:
    """NFL M13 -- tournament lineup-construction controls. Every field
    here is OFF/None by default, matching this project's "never
    silently restrictive" convention (Mock Mode, PRIVATE_BETA, etc.) --
    a caller that never sets any of these gets EXACTLY the pre-M13
    solver behavior, unchanged.

    Deliberately NOT a full min/max-receiver-count model -- "single" vs
    "double" QB stack and "off" vs "one" bring-back are the only shapes
    the UI (and this milestone's football-sense scope) actually needs;
    see config/nfl_optimizer_config.py for the exact receiver/bring-back
    counts each mode maps to."""

    qb_stack_mode: str = "off"  # "off" | "single" | "double"
    bring_back_mode: str = "off"  # "off" | "one"
    rb_dst_enabled: bool = False  # same-team RB + DST correlation
    max_players_per_team: Optional[int] = None
    max_players_per_game: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflOptimizerSettings:
    # "roster_feasibility" (M3), "projection" (M4), or NFL M13's
    # "ceiling"/"leverage" -- see nfl/objective.py for the per-mode
    # player-scoring formula and nfl/solver.py::generate_lineups() for
    # how each mode filters candidate eligibility.
    mode: str = "roster_feasibility"
    num_lineups: int = 1
    min_unique: int = 1
    locks: List[str] = field(default_factory=list)  # player keys (draftkings_player_id)
    excludes: List[str] = field(default_factory=list)
    salary_cap: int = DK_NFL_CLASSIC_SALARY_CAP
    time_limit_seconds: Optional[float] = None

    # NFL M13
    stack: NflStackConfig = field(default_factory=NflStackConfig)
    max_exposure: Dict[str, float] = field(default_factory=dict)  # player key -> fraction 0.0-1.0
    max_exposure_default: float = DEFAULT_MAX_EXPOSURE
    min_exposure: Dict[str, float] = field(default_factory=dict)  # player key -> fraction 0.0-1.0

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
    # NFL M12/M13: carried through from the NflOptimizerPlayer that
    # filled this slot -- None when Big Money Native has no estimate for
    # this player, never 0.0. Display only.
    projected_ownership: Optional[float] = None
    ceiling: Optional[float] = None

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
    # Explicit, unmissable label of which objective built this lineup --
    # always set explicitly by nfl/solver.py from the settings that
    # produced this lineup, never left at a stale default.
    mode: str = "roster_feasibility"
    # NFL M4: sum of each assigned player's real projection, only when
    # mode is a scoring mode that requires projection (None in
    # roster_feasibility mode -- there is no projection basis to sum,
    # and 0.0 would misleadingly imply one).
    total_projection: Optional[float] = None
    # NFL M13: sum of each assigned player's real ceiling -- None unless
    # EVERY assigned player has one (never a partial sum masquerading as
    # a total).
    total_ceiling: Optional[float] = None
    # NFL M13: sum/average of each assigned player's real ownership --
    # None unless EVERY assigned player has one. Mirrors optimizer/
    # models.py::Lineup's identical MLB convention.
    sum_ownership: Optional[float] = None
    average_ownership: Optional[float] = None
    # NFL M13: sum of each assigned player's real ownership leverage_score
    # -- only populated in "leverage" mode, and only when every assigned
    # player has one; None otherwise (never a partial/fabricated sum).
    total_leverage_score: Optional[float] = None
    # NFL M13 Phase 18 -- lineup-construction metadata, always computed
    # post-hoc from the ACTUAL assignment (never from "was the setting
    # on" alone -- a stack setting can be on with rb_dst yet still
    # produce a lineup where, say, the qb_stack_receiver_count differs
    # from what was requested is impossible by construction since the
    # solver enforces it, but bring_back_player reflects who was
    # actually rostered, not a hypothetical).
    qb_stack_team: Optional[str] = None  # the rostered QB's team, only when a real stack (>=1 same-team WR/TE) is present
    qb_stack_receiver_count: int = 0  # how many same-team WR/TE are actually rostered with the QB
    bring_back_player: Optional[str] = None  # name of the opposing RB/WR/TE satisfying bring-back, if any
    rb_dst_team: Optional[str] = None  # team where a rostered RB and the rostered DST match, if any

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "assignments": [a.to_dict() for a in self.assignments],
            "total_salary": self.total_salary,
            "remaining_salary": self.remaining_salary,
            "total_projection": self.total_projection,
            "total_ceiling": self.total_ceiling,
            "sum_ownership": self.sum_ownership,
            "average_ownership": self.average_ownership,
            "total_leverage_score": self.total_leverage_score,
            "draft_group_id": self.draft_group_id,
            "slate_date": self.slate_date,
            "sport": self.sport,
            "mode": self.mode,
            "qb_stack_team": self.qb_stack_team,
            "qb_stack_receiver_count": self.qb_stack_receiver_count,
            "bring_back_player": self.bring_back_player,
            "rb_dst_team": self.rb_dst_team,
        }

    def player_keys(self) -> List[str]:
        return [a.draftkings_player_id for a in self.assignments]


@dataclass
class NflGenerationResult:
    lineups: List[NflLineup]
    requested: int
    generated: int
    stopped_reason: Optional[str] = None  # set when generated < requested
