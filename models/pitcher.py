"""Typed data models for the Pitcher Agent.

These models are the contract between data-loading services and the
Pitcher Agent. Every statistical field is Optional: the agent must
tolerate missing non-critical data without inventing values.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List


@dataclass
class SeasonStats:
    innings: Optional[float] = None
    era: Optional[float] = None
    fip: Optional[float] = None
    xfip: Optional[float] = None
    siera: Optional[float] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    k_minus_bb_percent: Optional[float] = None
    swinging_strike_percent: Optional[float] = None
    csw_percent: Optional[float] = None
    ground_ball_percent: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    xera: Optional[float] = None
    xwoba_allowed: Optional[float] = None
    # Added for Statcast enrichment (Milestone 5). All Optional/None-default,
    # so every pre-existing SeasonStats(...) call site keeps working.
    xba: Optional[float] = None  # expected batting average against
    avg_exit_velocity_allowed: Optional[float] = None
    pitch_mix: Optional[Dict[str, float]] = None  # pitch_type -> usage percent, e.g. {"FF": 51.4, "SL": 30.2}
    # NOTE: season average fastball velocity is intentionally NOT duplicated
    # here -- it already lives at RecentStats.season_velocity (set in
    # Milestone 2) so the existing velocity_change = recent.velocity -
    # recent.season_velocity calculation keeps working unchanged.

    # Raw season event counts (Milestone 23). These were already being
    # fetched and parsed by research/enrichment.py::parse_season_pitching_stats
    # (battersFaced/strikeOuts/baseOnBalls/earnedRuns/hits/homeRuns/hitBatsmen
    # from the MLB Stats API) but were previously discarded before reaching
    # PitcherInput -- only the derived k_percent/bb_percent survived. The
    # Native Projection Model's hit/home-run/HBP/earned-run rate regression
    # needs real observed counts (not just percentages) to do count-based
    # empirical-Bayes shrinkage, so these are now carried through. No new
    # network call or invented data -- purely exposing what was already
    # being computed.
    batters_faced: Optional[int] = None
    strikeouts: Optional[int] = None
    walks: Optional[int] = None
    earned_runs: Optional[int] = None
    hits_allowed: Optional[int] = None
    home_runs_allowed: Optional[int] = None
    hit_by_pitch: Optional[int] = None


@dataclass
class RecentStats:
    innings: Optional[float] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    velocity: Optional[float] = None
    season_velocity: Optional[float] = None
    pitch_count_average: Optional[float] = None
    # Added for Statcast enrichment (Milestone 5): the same shape as the
    # season-level Statcast fields above, computed over the pitcher's last
    # 3 starts so the agent/research layer can compare recent vs. season
    # and detect trends. All Optional/None-default; backward compatible.
    csw_percent: Optional[float] = None
    swinging_strike_percent: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    ground_ball_percent: Optional[float] = None
    avg_exit_velocity_allowed: Optional[float] = None
    pitch_mix: Optional[Dict[str, float]] = None
    starts_sampled: Optional[int] = None  # how many of the "last 3" starts actually had data (sample-size honesty)

    # Raw recent-window event counts (Milestone 23), summed across the same
    # starts k_percent/bb_percent are computed from -- see
    # research/enrichment.py::parse_recent_pitching_stats. Lets the Native
    # Projection Model's sample-size-weighted recency blend use the real
    # recent opportunity count (batters_faced) instead of guessing it back
    # out of a percentage.
    batters_faced: Optional[int] = None
    strikeouts: Optional[int] = None
    walks: Optional[int] = None


@dataclass
class OpponentStats:
    team: Optional[str] = None
    strikeout_percent_vs_hand: Optional[float] = None
    # Overall (not handedness-specific) team strikeout rate. Populated as a
    # temporary stand-in when true vs-hand splits aren't available yet --
    # `strikeout_percent_split_type` records which kind this is so callers
    # never mistake one for the other. See agents/pitcher_agent.py's
    # `_opponent_k_percent` for the fallback order.
    strikeout_percent: Optional[float] = None
    strikeout_percent_split_type: Optional[str] = None  # "overall" | "vs_hand"
    woba_vs_hand: Optional[float] = None
    iso_vs_hand: Optional[float] = None
    implied_runs: Optional[float] = None


@dataclass
class GameContext:
    park_factor: Optional[float] = None
    weather_pitching_factor: Optional[float] = None
    umpire_pitching_factor: Optional[float] = None


@dataclass
class Availability:
    confirmed_starter: Optional[bool] = None
    expected_pitch_count: Optional[float] = None


@dataclass
class TrendMetrics:
    """Derived research (recent vs. season deltas), computed once by the
    Research Engine (research/statcast_enrichment.py) so neither the
    Pitcher Agent nor any other consumer has to recompute it. A positive
    value always means "moved in the pitcher-favorable direction" for
    that metric (e.g. velocity_trend > 0 = velocity increased;
    hard_hit_trend > 0 = hard-hit rate ALLOWED went down -- see the
    field-level docstring on each)."""

    velocity_trend: Optional[float] = None       # recent velocity - season velocity (mph)
    csw_trend: Optional[float] = None             # recent CSW% - season CSW% (points)
    swinging_strike_trend: Optional[float] = None  # recent SwStr% - season SwStr% (points)
    # Contact-quality trends are inverted so "positive = better for the
    # pitcher" stays consistent across every *_trend field: a DROP in
    # hard-hit/barrel rate is favorable, so hard_hit_trend/barrel_trend
    # are (season - recent), not (recent - season).
    hard_hit_trend: Optional[float] = None
    barrel_trend: Optional[float] = None
    ground_ball_trend: Optional[float] = None      # recent GB% - season GB% (points; more grounders is generally favorable)
    pitch_mix_change: Optional[float] = None       # sum of |recent_usage - season_usage| across pitch types (0 = no change)


@dataclass
class PitcherInput:
    """Normalized pitcher record consumed by the Pitcher Agent."""

    player_id: str
    name: str
    team: str
    opponent: str
    # No DFS salary source exists yet (no DK/FD CSV ingestion). Real
    # pitchers built from the Research Engine always carry salary=None --
    # it is never invented.
    salary: Optional[int] = None
    throwing_hand: Optional[str] = None
    # Identity/join keys back to the Research Package (informational only;
    # the agent's scoring logic never reads these).
    game_id: Optional[str] = None
    venue_name: Optional[str] = None

    season: SeasonStats = field(default_factory=SeasonStats)
    recent: RecentStats = field(default_factory=RecentStats)
    opponent_stats: OpponentStats = field(default_factory=OpponentStats)
    game: GameContext = field(default_factory=GameContext)
    availability: Availability = field(default_factory=Availability)
    trends: TrendMetrics = field(default_factory=TrendMetrics)

    @classmethod
    def from_dict(cls, data: dict) -> "PitcherInput":
        salary = data.get("salary")
        return cls(
            player_id=str(data["player_id"]),
            name=data["name"],
            team=data["team"],
            opponent=data["opponent"],
            salary=int(salary) if salary is not None else None,
            throwing_hand=data.get("throwing_hand"),
            game_id=data.get("game_id"),
            venue_name=data.get("venue_name"),
            season=SeasonStats(**data.get("season", {})),
            recent=RecentStats(**data.get("recent", {})),
            opponent_stats=OpponentStats(**data.get("opponent_stats", {})),
            game=GameContext(**data.get("game", {})),
            availability=Availability(**data.get("availability", {})),
            trends=TrendMetrics(**data.get("trends", {})),
        )


@dataclass
class PitcherBoardEntry:
    """Output of the Pitcher Agent for a single pitcher."""

    player_id: str
    name: str
    team: str
    opponent: str

    projection: float
    ceiling: float
    floor: float

    overall_score: float
    strikeout_score: float
    run_prevention_score: float
    matchup_score: float
    workload_score: float
    contact_score: float
    environment_score: float
    value_score: float

    risk_score: float
    confidence: float

    # No DFS salary source exists yet; real-data boards leave this None
    # rather than inventing a price.
    salary: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
