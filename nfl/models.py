"""NFL M2 -- the canonical NFL DraftKings player pool.

Deliberately NOT dfs/models.py::DFSPlayer -- that dataclass's semantics
(player_type: "pitcher"|"hitter", batting_order, throwing_hand,
batting_hand, mlb_player_id, MLB-only eligibility statuses) are
baseball-specific, not generic. NflPlayer is a fresh model reflecting
NFL Classic's real shape, built directly from DraftKings' own raw
draftable/game data (draftkings_unofficial/models.py's DkDraftable/
DkSlateGame) rather than through dfs/providers/adapter.py's
ProviderPlayer/DKSalaryRow intermediate -- that intermediate exists to
keep MLB's CSV and provider paths byte-compatible, a constraint NFL
doesn't have, and it drops fields (draftable_id, roster_slot_id,
status, competition_id) real NFL data needs.

Mirrors the Optional-everywhere, never-invent-a-value discipline of
dfs/models.py and draftkings_unofficial/normalizer.py (whose own
docstring is the reason avg_points_per_game/fppg-style fields are
deliberately absent here too -- draftStatAttributes ids have no
self-describing label anywhere in the payloads this project has
observed, so nothing is guessed from them)."""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

# DraftKings' own NFL Classic roster-slot vocabulary (base positions
# plus the shared FLEX slot) -- never a player's own `position` value,
# which stays their true position even when they're also FLEX-eligible.
NFL_BASE_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "DST"})
FLEX_SLOT_NAME = "FLEX"


@dataclass
class NflPlayer:
    """One canonical NFL Classic player (or, for position == "DST", one
    team defense/special-teams entity -- DraftKings models it with the
    identical schema as a person, so `is_team_entity` is the only signal
    that distinguishes it; see DST's real payload in NFL M2's own
    investigation notes)."""

    draftkings_player_id: str  # DK's stable cross-slate playerId -- canonical identity for M2
    draftkings_dk_id: Optional[str]  # DK's separate playerDkId, preserved alongside, never discarded
    draftable_ids: List[str]  # one per real raw row (base slot, plus FLEX row when eligible)
    name: str
    first_name: Optional[str]
    last_name: Optional[str]
    is_team_entity: bool  # True only for position == "DST"

    position: str  # QB | RB | WR | TE | DST -- a player's true position, never "FLEX"
    roster_slots: List[str]  # e.g. ["RB", "FLEX"] or ["QB"] or ["DST"] -- FLEX kept separate, never collapsed into position

    team: str
    opponent: Optional[str]
    game_id: str  # DK's own competitionId, stringified -- structural, never text-parsed
    game_description: Optional[str]  # DK's own "AWAY @ HOME" string, display-only
    game_start_time: Optional[str]

    salary: int

    status: Optional[str]  # DK's raw status string ("None"/"Q"/etc.), verbatim
    injury_status: Optional[str]  # None when status is None/"None", else the same value -- explicit, never inferred

    draft_group_id: int
    slate_date: str
    slate_name: Optional[str]

    source: str  # "draftkings_unofficial"
    source_provenance: str  # "DRAFTKINGS_UNOFFICIAL_LIVE" -- only ever set once structural validation has passed

    # Never invented: both stay None until a real NFL projection/
    # ownership stage exists (NFL M4+/M6+, not built in M2).
    projection: Optional[float] = None
    ownership: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflPoolValidationFinding:
    level: str  # "BLOCK" | "WARN"
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflPoolValidationResult:
    passed: bool
    findings: List[NflPoolValidationFinding] = field(default_factory=list)

    total_players: int = 0
    position_counts: Dict[str, int] = field(default_factory=dict)
    team_count: int = 0
    game_count: int = 0
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "findings": [f.to_dict() for f in self.findings],
            "total_players": self.total_players,
            "position_counts": self.position_counts,
            "team_count": self.team_count,
            "game_count": self.game_count,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
        }


@dataclass
class NflPoolBuildResult:
    draft_group_id: int
    slate_date: str
    slate_name: Optional[str]
    players: List[NflPlayer]
    validation: NflPoolValidationResult
    source_provenance: str

    def to_dict(self) -> dict:
        return {
            "draft_group_id": self.draft_group_id,
            "slate_date": self.slate_date,
            "slate_name": self.slate_name,
            "source_provenance": self.source_provenance,
            "validation": self.validation.to_dict(),
            "players": [p.to_dict() for p in self.players],
        }
