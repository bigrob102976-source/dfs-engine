"""Typed schemas for the shared MLB Research Engine.

These are pure data containers describing what the Research Engine knows
about a slate. They carry no scoring, projection, or DFS logic — that
stays in agents/ (e.g. agents/pitcher_agent.py), which will eventually
consume this package instead of downloading its own data.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Team:
    team_id: str
    abbreviation: str
    name: str
    league: Optional[str] = None
    division: Optional[str] = None


@dataclass
class Game:
    game_id: str
    date: str
    game_datetime_utc: Optional[str]
    status: str
    home_team_id: str
    home_team_abbr: str
    away_team_id: str
    away_team_abbr: str
    venue_id: Optional[str] = None
    venue_name: Optional[str] = None
    home_probable_pitcher_id: Optional[str] = None
    away_probable_pitcher_id: Optional[str] = None
    game_number: Optional[int] = None


@dataclass
class PitcherRecord:
    """A probable starting pitcher known to the Research Engine.

    This is deliberately thin (identity + role, not skill). Advanced
    pitching metrics (SIERA, xFIP, Statcast, etc.) are not collected by
    this milestone's collector; see `statcast_metadata` in slate.json.
    """

    player_id: str
    name: str
    team_id: str
    team_abbr: str
    opponent_team_id: str
    opponent_abbr: str
    game_id: str
    throws: Optional[str] = None
    status: str = "probable"
    source: str = "mlb_stats_api"


@dataclass
class BatterRecord:
    """A starting-lineup batter, when lineups have been posted."""

    player_id: str
    name: str
    team_id: str
    team_abbr: str
    opponent_team_id: str
    opponent_abbr: str
    game_id: str
    batting_order: Optional[int] = None
    position: Optional[str] = None
    bats: Optional[str] = None
    status: str = "starting_lineup"
    source: str = "mlb_stats_api"


@dataclass
class ValidationIssue:
    level: str  # "warning" or "error"
    message: str


@dataclass
class ResearchMetadata:
    slate_date: str
    generated_at: str
    sources_used: List[str]
    version: str
    pipeline_duration_seconds: float
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SlateIndex:
    """The top-level pointer object (slate.json) future agents load first."""

    slate_date: str
    game_ids: List[str]
    team_ids: List[str]
    counts: Dict[str, int]
    files: Dict[str, str]
    # Categories with no dedicated file this milestone. Kept as an explicit,
    # empty, schema-shaped placeholder rather than omitted, per "never
    # silently discard information" — the gap itself is information.
    bullpens: List[dict] = field(default_factory=list)
    statcast_metadata: List[dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NormalizedPackage:
    games: List[Game]
    teams: List[Team]
    pitchers: List[PitcherRecord]
    batters: List[BatterRecord]
    warnings: List[str]


@dataclass
class ResearchReport:
    slate_date: str
    games_found: int
    teams_found: int
    pitchers_found: int
    batters_found: int
    warnings: List[str]
    errors: List[str]
    files_written: Dict[str, str]
    duration_seconds: float
