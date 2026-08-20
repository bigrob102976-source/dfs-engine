"""Normalized data models for the unofficial DraftKings provider.

Every model carries `raw: dict` (the untouched source object this
record was normalized from) so nothing observed from the live API is
ever lost, even when a field isn't promoted to a named attribute --
see this milestone's "do not restrict collection to fields we
currently think we need" requirement. Sport-agnostic by design: no
field here assumes MLB positions/roster slots/scoring.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DkSport:
    """One sport DraftKings currently exposes -- from
    /sites/US-DK/sports/v1/sports."""

    sport_id: int
    code: str  # regionAbbreviatedSportName, e.g. "MLB", "NFL", "NAS"
    full_name: str
    has_public_contests: bool
    is_enabled: bool
    sort_order: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DkGameType:
    """One game type (Classic, Showdown Captain Mode, Tiers, ...) for a
    sport -- from getcontests's GameTypes list."""

    game_type_id: int
    sport_id: int
    name: str
    description: Optional[str] = None
    draft_type: Optional[str] = None  # "SalaryCap" | "Tiered" | ...
    is_season_long: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DkRosterSlot:
    """One roster slot within a game type's lineup template (e.g. "P",
    "OF", "CPT", "UTIL") -- from /lineups/v1/gametypes/{id}/rules."""

    roster_slot_id: int
    name: str
    description: Optional[str] = None
    order: Optional[int] = None
    # DK exposes a multiplier (e.g. Showdown Captain's 1.5x) only as
    # free text in positionTipSubtext ("1.5x") -- never a clean numeric
    # field. Parsed defensively; None when not present/parseable, never
    # guessed. See normalizer.py::_parse_multiplier.
    scoring_multiplier: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DkRosterRules:
    """Roster/salary-cap rules for one game type -- from
    /lineups/v1/gametypes/{id}/rules. DraftKings does NOT expose a
    machine-readable points-per-stat scoring formula through this or
    any other endpoint found during this milestone's discovery -- only
    `rules_url`, a link to a human-readable help page. See this
    module's docstring and the milestone report's "scoring rules"
    finding; never fabricated here."""

    game_type_id: int
    sport_id: Optional[int]
    name: str
    draft_type: Optional[str]
    salary_cap_enabled: bool
    salary_cap: Optional[int]
    roster_slots: List[DkRosterSlot] = field(default_factory=list)
    unique_players: Optional[bool] = None
    allow_late_swap: Optional[bool] = None
    min_games: Optional[int] = None
    min_teams: Optional[int] = None
    rules_url: Optional[str] = None  # human-readable only, never parsed for scoring math
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class DkTeam:
    team_id: int
    abbreviation: str
    name: Optional[str] = None
    city: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DkSlateGame:
    """One event/competition within a slate -- from draftables'
    `competitions` list. Called "SlateGame" (not just "Game") because
    it's scoped to one DraftGroup's view of the event."""

    competition_id: int
    sport_id: Optional[int]
    name: Optional[str]
    start_time: Optional[str]
    home_team: Optional[DkTeam] = None
    away_team: Optional[DkTeam] = None
    venue: Optional[str] = None
    state: Optional[str] = None  # competitionState, e.g. "Upcoming"
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class DkDraftable:
    """One salaried, selectable entity for a slate -- a player, but
    also possibly a driver/golfer/DST/team depending on sport/format.
    "Draftable" (DraftKings' own term), never assumed to be an athlete."""

    draftable_id: int
    draft_group_id: int
    player_id: Optional[int]  # DK's stable cross-slate player identity
    player_dk_id: Optional[int]  # DK's own separate "playerDkId" (distinct field, both preserved)
    display_name: str
    first_name: Optional[str]
    last_name: Optional[str]
    position: Optional[str]
    roster_slot_id: Optional[int]
    salary: Optional[int]
    status: Optional[str]  # DK's own free-text status, e.g. "None", "Q", "O"
    team_id: Optional[int]
    team_abbreviation: Optional[str]
    competition_id: Optional[int]
    is_swappable: Optional[bool] = None
    is_disabled: Optional[bool] = None
    news_status: Optional[str] = None
    fppg: Optional[float] = None  # from draftStatAttributes, when identifiable -- see normalizer.py
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DkContest:
    """One entrant-facing contest -- from getcontests's Contests list.
    Complete raw metadata is preserved in `raw`; only the fields this
    milestone explicitly asked to normalize are promoted."""

    contest_id: int
    name: str
    sport_id: Optional[int]
    draft_group_id: Optional[int]
    game_type: Optional[str]
    game_type_id: Optional[int]
    start_time_raw: Optional[str]  # DK's own /Date(ms)/ string, unparsed -- see normalizer.py for the parsed ISO version
    start_time_iso: Optional[str]
    entry_fee: Optional[float] = None
    prize_pool: Optional[float] = None
    max_entries: Optional[int] = None
    current_entries: Optional[int] = None
    max_entries_per_user: Optional[int] = None
    is_guaranteed: Optional[bool] = None
    is_starred: Optional[bool] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DkSlate:
    """A DraftGroup, treated as the temporary canonical DraftKings slate
    identifier per this milestone -- confirmed live that many contests
    can share one DraftGroupId (see normalizer.py's dedup)."""

    draft_group_id: int
    sport_id: int
    sport_code: str
    game_type_id: int
    game_type_name: Optional[str]
    start_time: Optional[str]
    tag: Optional[str] = None  # DraftKings' own DraftGroupTag (e.g. "Featured"), never invented as "Main"/"Early"
    label: Optional[str] = None  # DraftKings' own ContestStartTimeSuffix (e.g. " (Night)", " (NYY @ BAL)"), when present
    game_count: Optional[int] = None
    contest_ids: List[int] = field(default_factory=list)
    games: List[DkSlateGame] = field(default_factory=list)
    draftables: List[DkDraftable] = field(default_factory=list)
    roster_rules: Optional[DkRosterRules] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "draft_group_id": self.draft_group_id, "sport_id": self.sport_id, "sport_code": self.sport_code,
            "game_type_id": self.game_type_id, "game_type_name": self.game_type_name, "start_time": self.start_time,
            "tag": self.tag, "label": self.label, "game_count": self.game_count, "contest_ids": self.contest_ids,
            "games": [g.to_dict() for g in self.games], "draftables": [d.to_dict() for d in self.draftables],
            "roster_rules": self.roster_rules.to_dict() if self.roster_rules else None, "raw": self.raw,
        }


@dataclass
class PlayerIdentityMatch:
    """A durable provider-ID -> canonical-identity mapping attempt for
    ONE draftable -- see identity.py. Ambiguous/unmatched results are
    preserved, never silently dropped or guessed."""

    draftable_id: int
    provider_player_id: Optional[int]
    display_name: str
    sport_code: str
    match_status: str  # "matched" | "unmatched" | "ambiguous"
    canonical_player_id: Optional[str] = None
    match_confidence: Optional[str] = None
    candidate_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
