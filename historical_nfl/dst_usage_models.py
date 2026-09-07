"""NFL M8 -- the canonical NFL DST (team defense/special-teams) usage
record. Team-level, not player-level: DST's real DK identity is
`dst:{team}` (see historical_nfl/identity_models.py's module docstring
and identity_matching.py::build_dst_crosswalk_row()) -- this module
never attaches a synthetic GSIS ID to a team-defense entity.

Field provenance (Phase 1 audit, confirmed live 2025 Week 1):
  - sacks/interceptions/defensive_tds: DIRECT from nflreadpy.load_team_
    stats()'s own def_sacks/def_interceptions/def_tds columns -- that
    dataset's def_* columns are the requesting team's OWN defensive
    stats (paired with def_tackles_solo/def_qb_hits in the same row,
    unambiguous), not stats committed against them.
  - points_allowed: DERIVED from nflreadpy.load_schedules() -- the
    opponent's real final score in that game_id (home_score when this
    team was away, away_score when this team was home).
  - yards_allowed: DERIVED from the OPPONENT's own load_team_stats() row
    for the same game_id (their passing_yards + rushing_yards -- the
    standard "total yards" definition), i.e. what the opponent's offense
    gained, which is exactly what this team's defense allowed.

Deliberately NOT included this milestone: fumbles recovered by the
defense. nflreadpy ships no public data dictionary for load_team_stats()
in this version (checked live), and the candidate column
(`fumble_recovery_opp`) has an ambiguous enough name that this milestone
declines to guess its exact semantics rather than risk misattributing a
real stat -- see historical_nfl/dst_usage_normalize.py's module
docstring."""

from dataclasses import asdict, dataclass
from typing import Optional

DST_SCHEMA_VERSION = "nfl_dst_usage_v1"
SOURCE_TEAM_STATS_DERIVED = "nflverse_team_stats_derived"


@dataclass
class NflDstUsageRecord:
    team: str  # DraftKings' own NFL team abbreviation -- see config/nfl_team_abbreviations.py
    opponent: Optional[str]
    season: int
    week: int
    game_id: Optional[str]

    sacks: Optional[float] = None  # fractional -- shared sacks split 0.5/0.5 by nflverse itself
    interceptions: Optional[int] = None
    defensive_tds: Optional[int] = None

    points_allowed: Optional[int] = None
    yards_allowed: Optional[int] = None

    source: str = SOURCE_TEAM_STATS_DERIVED
    source_provenance: Optional[str] = None
    ingested_at: Optional[str] = None

    schema_version: str = DST_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)
