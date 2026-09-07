"""NFL M11 -- the canonical team-offense-output record: what ONE team's
OWN offense did in one real game, used to build the opponent-context
layer DST projections were missing in M10 (see historical_models/nfl_v1
/train.py's M10 audit -- DST's own prior sacks/INTs/points-allowed says
nothing about whether next week's OPPONENT is a turnover-prone bad
offense or an elite one, which is a large real driver of week-to-week
DST fantasy variance).

Field provenance (real, DIRECT nflreadpy.load_team_stats() columns,
confirmed live -- same dataset historical_nfl/dst_usage_models.py
already audits):
  - points_scored: DERIVED from nflreadpy.load_schedules() (this team's
    own real final score in that game_id) -- team_stats has no direct
    points column.
  - total_yards: passing_yards + rushing_yards (this team's OWN
    offensive output -- see dst_usage_models.py's module docstring for
    why these two summed is the standard "total yards" definition).
  - turnovers: passing_interceptions + fumbles_lost_total (both DIRECT,
    real columns -- how many times this team's own offense gave the
    ball away).
  - sacks_allowed: sacks_suffered (DIRECT -- how many times this team's
    OWN offense was sacked, i.e. what a defense facing them next week
    might do again).
  - pass_attempts / rush_attempts: attempts / carries (DIRECT)."""

from dataclasses import asdict, dataclass
from typing import Optional

TEAM_OFFENSE_SCHEMA_VERSION = "nfl_team_offense_v1"
SOURCE_TEAM_STATS_DERIVED = "nflverse_team_stats_derived"


@dataclass
class NflTeamOffenseRecord:
    team: str
    opponent: Optional[str]
    season: int
    week: int
    game_id: Optional[str]

    points_scored: Optional[int] = None
    total_yards: Optional[int] = None
    turnovers: Optional[int] = None
    sacks_allowed: Optional[float] = None
    pass_attempts: Optional[int] = None
    rush_attempts: Optional[int] = None

    source: str = SOURCE_TEAM_STATS_DERIVED
    ingested_at: Optional[str] = None
    schema_version: str = TEAM_OFFENSE_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)
