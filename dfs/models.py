"""Typed data models for DraftKings ingestion and the unified DFS player
pool. Mirrors the Optional-everywhere, never-invent-a-value discipline
of models/pitcher.py and models/batter.py.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class DKSalaryRow:
    """One row of a DraftKings salary CSV, parsed but not yet matched to
    an MLB player. DraftKings is authoritative for every field here."""

    dk_player_id: str
    name: str
    team_abbrev: str
    dk_positions: List[str]
    salary: int
    game_info: str
    avg_points_per_game: Optional[float] = None
    roster_position_raw: Optional[str] = None

    # Milestone 27.4: source-to-pool trace -- lets an admin/debug view
    # trace any normalized player back to the exact raw source row it
    # came from. Populated only by dfs/draftkings_parser.py (a real CSV
    # file on disk has a row number/filename/hash); left None for rows
    # built from a provider adapter, which has no single raw file.
    source_row_number: Optional[int] = None
    source_filename: Optional[str] = None
    source_sha256: Optional[str] = None


@dataclass
class CanonicalPlayer:
    """One player identity known to our Research Engine (a probable
    starting pitcher, or a hitter in a posted starting lineup)."""

    mlb_player_id: str
    name: str
    team: str
    opponent: str
    game_id: str
    player_type: str  # "pitcher" | "hitter"


@dataclass
class PlayerMatch:
    """Result of resolving one DKSalaryRow to (at most) one CanonicalPlayer."""

    dk_player_id: str
    dk_name: str
    dk_team: str
    match_status: str  # "matched" | "unmatched" | "ambiguous"
    mlb_player_id: Optional[str] = None
    match_confidence: Optional[str] = None  # "explicit_crosswalk" | "name_team_exact" | "name_only_slate_unique"
    player_type: Optional[str] = None  # known when matched, or inferred from DK position when unmatched
    candidate_mlb_ids: List[str] = field(default_factory=list)
    candidate_names: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DFSPlayer:
    """One unified, optimizer-ready (or excluded-with-reason) DFS player:
    DraftKings salary/position identity joined with our own model's
    pregame projection, when both are available."""

    dk_player_id: str
    name: str
    team: str
    player_type: str  # "pitcher" | "hitter"
    dk_positions: List[str]
    salary: int

    mlb_player_id: Optional[str] = None
    opponent: Optional[str] = None
    game_id: Optional[str] = None

    batting_order: Optional[int] = None
    throwing_hand: Optional[str] = None
    batting_hand: Optional[str] = None

    projection: Optional[float] = None
    ceiling: Optional[float] = None
    floor: Optional[float] = None

    overall_score: Optional[float] = None
    risk_score: Optional[float] = None
    confidence: Optional[float] = None

    tags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    season_sample_size: Optional[float] = None
    recent_sample_size: Optional[float] = None

    source_model_type: Optional[str] = None  # "pitcher" | "batter"
    source_model_version: Optional[str] = None
    prediction_generated_at_utc: Optional[str] = None
    prediction_generated_at_local: Optional[str] = None
    prediction_snapshot_path: Optional[str] = None

    # active | lineup_not_confirmed | not_in_starting_lineup | unmatched |
    # game_not_on_research_slate | missing_projection
    lineup_status: str = "unmatched"
    match_status: str = "unmatched"  # matched | unmatched | ambiguous
    match_confidence: Optional[str] = None

    avg_points_per_game_dk: Optional[float] = None  # DK's own metric, preserved but never fed into our model

    # Milestone 27.4: source-to-pool trace -- see DKSalaryRow's identical
    # fields, which these are copied verbatim from.
    source_row_number: Optional[int] = None
    source_filename: Optional[str] = None
    source_sha256: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RosterFeasibilityResult:
    passed: bool
    reasons: List[str]
    position_counts: Dict[str, int]
    pitcher_count: int
    games_represented: int

    def to_dict(self) -> dict:
        return asdict(self)
