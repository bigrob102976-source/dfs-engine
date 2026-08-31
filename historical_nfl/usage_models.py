"""NFL M6C Phase 3 -- the durable, normalized NFL usage record.

Every field is Optional and left None unless it can be honestly sourced
or derived from a real, audited nflverse field -- NULL != 0 throughout
(a player with no recorded targets is None, never 0, unless the source
itself reports a real zero for a player known to have played).

Denominator definitions (Phase 7, audited live during M6C against real
2025 Week 1 data -- see historical_nfl/usage_normalize.py's module
docstring for the full audit trail):
  - target_share: player targets / SUM of every player's targets on
    that team+week, both sides read from nflreadpy.load_player_stats()'s
    own `targets` field -- self-consistent (shares sum to 1.0 exactly),
    using nflverse's own official target definition rather than a raw
    play-by-play proxy with an unexplained ~7% discrepancy found during
    the audit (45 vs 48 for a real team/week -- not fully understood,
    so not relied on).
  - carry_share: player rush attempts / team rush attempts, BOTH computed
    from play-by-play with `qb_kneel` EXCLUDED from both sides -- audited
    live and confirmed nflreadpy.load_player_stats()'s own `carries`
    field INCLUDES kneels (a real team's weekly_player_stats carries sum
    matched PBP rush_attempt==1 including kneels, not excluding them),
    which would silently dilute every real ball-carrier's share with
    garbage-time kneel-downs -- exactly the failure mode Phase 7 warned
    against, so carry_share is computed independently from PBP instead
    of reusing the M6A weekly_player_stats aggregate.
  - snap_share: taken directly from nflreadpy.load_snap_counts()'s own
    `offense_pct` field (Pro-Football-Reference's own computed share) --
    NOT re-derived by Big Money, since PFR already has the correct
    team-offensive-snap denominator and re-deriving it independently
    would only risk introducing a second, competing definition.

routes / route_participation are left None for EVERY record in M6C --
see historical_nfl/usage_normalize.py's module docstring for why
nflverse's real load_participation() data does not decompose into a
trustworthy per-player route count without an inference this milestone
was explicitly told not to make."""

from dataclasses import asdict, dataclass
from typing import Optional

SCHEMA_VERSION = "nfl_usage_v1"

SOURCE_SNAP_COUNTS = "nflverse_snap_counts"
SOURCE_WEEKLY_STATS_DERIVED = "nflverse_weekly_player_stats_derived"
SOURCE_PBP_DERIVED = "nflverse_play_by_play_derived"


@dataclass
class NflUsageRecord:
    canonical_player_id: Optional[str]  # None when gsis_id has no M6B crosswalk mapping yet -- see Phase 5
    gsis_id: str

    season: int
    week: int
    game_id: Optional[str]

    team: Optional[str]
    opponent: Optional[str]
    position: Optional[str]

    offensive_snaps: Optional[float] = None
    defensive_snaps: Optional[float] = None
    special_teams_snaps: Optional[float] = None
    snap_share: Optional[float] = None  # sourced from PFR's own offense_pct, not derived here

    targets: Optional[int] = None
    target_share: Optional[float] = None  # DERIVED -- see module docstring

    receptions: Optional[int] = None

    carries: Optional[int] = None
    carry_share: Optional[float] = None  # DERIVED -- see module docstring

    routes: Optional[int] = None  # never populated in M6C -- see module docstring
    route_participation: Optional[float] = None  # never populated in M6C

    red_zone_targets: Optional[int] = None  # DERIVED from M6A play-by-play
    red_zone_carries: Optional[int] = None  # DERIVED from M6A play-by-play
    goal_line_carries: Optional[int] = None  # DERIVED from M6A play-by-play

    source: str = SOURCE_WEEKLY_STATS_DERIVED
    source_provenance: Optional[str] = None

    event_time: Optional[str] = None
    available_at: Optional[str] = None  # always None -- nflverse supplies no true publication timestamp (never invented, per Phase 10)
    ingested_at: Optional[str] = None

    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)
