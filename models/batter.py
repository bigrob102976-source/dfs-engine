"""Typed data models for the Batter Agent.

Mirrors models/pitcher.py's contract exactly: every statistical field is
Optional, nothing here is ever populated with an invented value, and the
Batter Agent must tolerate any of it being missing.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class SeasonBattingStats:
    plate_appearances: Optional[int] = None
    at_bats: Optional[int] = None
    hits: Optional[int] = None
    doubles: Optional[int] = None
    triples: Optional[int] = None
    home_runs: Optional[int] = None
    walks: Optional[int] = None
    strikeouts: Optional[int] = None
    stolen_bases: Optional[int] = None

    avg: Optional[float] = None
    obp: Optional[float] = None
    slg: Optional[float] = None
    ops: Optional[float] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    iso: Optional[float] = None
    woba: Optional[float] = None  # Statcast's own wOBA (real internal linear weights, not our approximation)

    # Statcast (season)
    xwoba: Optional[float] = None
    xba: Optional[float] = None
    xslg: Optional[float] = None
    exit_velocity: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    launch_angle: Optional[float] = None
    sweet_spot_percent: Optional[float] = None
    bat_speed: Optional[float] = None          # Savant's avg_swing_speed
    squared_up_percent: Optional[float] = None  # not reliably exposed by the current source; stays None

    pitch_type_performance: Optional[Dict[str, float]] = None  # pitch_type -> wOBA, season-long (recent-window equivalent is on RecentBattingStats)


@dataclass
class RecentBattingStats:
    """Last-14-days window (see research/batter_enrichment.py /
    research/statcast_batter_enrichment.py for exactly how each field is
    computed and from which source)."""

    plate_appearances: Optional[int] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None

    xwoba: Optional[float] = None
    exit_velocity: Optional[float] = None
    max_exit_velocity: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    launch_angle: Optional[float] = None

    pitch_type_performance: Optional[Dict[str, float]] = None  # pitch_type -> wOBA, recent window only
    sample_size_pitches: Optional[int] = None  # total pitches seen in the window (raw sample-size honesty)
    days_sampled: Optional[int] = None


@dataclass
class PlatoonSplitStats:
    """One side of a batter's platoon performance (vs RHP or vs LHP)."""

    plate_appearances: Optional[int] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    iso: Optional[float] = None
    woba: Optional[float] = None
    ops: Optional[float] = None
    # "vs_hand" = a true MLB Stats API handedness split (sitCodes vr/vl).
    # There is currently no "overall fallback" case for batters (the split
    # endpoint has proven reliable), but this field exists so nothing
    # downstream ever has to guess what kind of number it's looking at --
    # see agents/pitcher_agent.py's OpponentStats.strikeout_percent_split_type
    # for the same honesty pattern applied to pitcher research.
    split_type: Optional[str] = None


@dataclass
class OpposingPitcherContext:
    """Raw/contextual metrics for the confirmed opposing starter, sourced
    from the SAME research.enrichment / research.statcast_enrichment
    pipeline the Pitcher Agent uses -- never the Pitcher Agent's scores,
    tags, or ranking. See research/opposing_pitcher_context.py."""

    player_id: Optional[str] = None
    name: Optional[str] = None
    throwing_hand: Optional[str] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    xera: Optional[float] = None
    xwoba_allowed: Optional[float] = None
    hard_hit_percent_allowed: Optional[float] = None
    barrel_percent_allowed: Optional[float] = None
    ground_ball_percent: Optional[float] = None
    velocity: Optional[float] = None
    csw_percent: Optional[float] = None


@dataclass
class TrendMetrics:
    """Recent-vs-season deltas. A positive value always means "moved in
    the HITTER'S favor" for that metric -- strikeout_rate_trend is
    inverted (season - recent) since a lower K% is good for a hitter,
    the opposite convention from the other four fields."""

    exit_velocity_trend: Optional[float] = None
    hard_hit_trend: Optional[float] = None
    barrel_trend: Optional[float] = None
    xwoba_trend: Optional[float] = None
    strikeout_rate_trend: Optional[float] = None  # season k% - recent k% (positive = fewer Ks recently = good)
    walk_rate_trend: Optional[float] = None       # recent bb% - season bb% (positive = more walks recently = good)


@dataclass
class BatterInput:
    """Normalized hitter record consumed by the Batter Agent. Only ever
    built for hitters in a POSTED starting lineup -- see
    research/adapters/batter_input.py."""

    player_id: str
    name: str
    team: str
    opponent: str
    game_id: Optional[str] = None
    venue_name: Optional[str] = None
    batting_hand: Optional[str] = None
    batting_order: Optional[int] = None
    position: Optional[str] = None
    # No DFS salary source exists yet -- never invented, always None in
    # research mode.
    salary: Optional[int] = None

    season: SeasonBattingStats = field(default_factory=SeasonBattingStats)
    recent: RecentBattingStats = field(default_factory=RecentBattingStats)
    vs_rhp: PlatoonSplitStats = field(default_factory=PlatoonSplitStats)
    vs_lhp: PlatoonSplitStats = field(default_factory=PlatoonSplitStats)
    opposing_pitcher: OpposingPitcherContext = field(default_factory=OpposingPitcherContext)
    trends: TrendMetrics = field(default_factory=TrendMetrics)

    @classmethod
    def from_dict(cls, data: dict) -> "BatterInput":
        salary = data.get("salary")
        return cls(
            player_id=str(data["player_id"]),
            name=data["name"],
            team=data["team"],
            opponent=data["opponent"],
            game_id=data.get("game_id"),
            venue_name=data.get("venue_name"),
            batting_hand=data.get("batting_hand"),
            batting_order=data.get("batting_order"),
            position=data.get("position"),
            salary=int(salary) if salary is not None else None,
            season=SeasonBattingStats(**data.get("season", {})),
            recent=RecentBattingStats(**data.get("recent", {})),
            vs_rhp=PlatoonSplitStats(**data.get("vs_rhp", {})),
            vs_lhp=PlatoonSplitStats(**data.get("vs_lhp", {})),
            opposing_pitcher=OpposingPitcherContext(**data.get("opposing_pitcher", {})),
            trends=TrendMetrics(**data.get("trends", {})),
        )


@dataclass
class BatterBoardEntry:
    """Output of the Batter Agent for a single hitter."""

    player_id: str
    name: str
    team: str
    opponent: str
    batting_order: Optional[int]

    projection: float
    ceiling: float
    floor: float

    overall_score: float
    hitting_skill_score: float
    power_score: float
    contact_score: float
    matchup_score: float
    recent_trend_score: float
    lineup_position_score: float
    environment_score: float
    value_score: float

    risk_score: float
    confidence: float

    salary: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
