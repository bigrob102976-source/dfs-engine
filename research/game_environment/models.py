"""Typed data shapes for the Game Environment Engine (Milestone DS2).

Mirrors the Optional-everywhere, never-invent-a-value discipline of
models/pitcher.py and models/batter.py, and external_projections/models.py's
normalized-provider-output pattern: nothing downstream of this package
should ever need to know which concrete weather/vegas/umpire/bullpen
provider supplied a value, and a missing signal stays None/UNKNOWN
rather than being guessed.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


# ----------------------------------------------------------------------------
# Weather
# ----------------------------------------------------------------------------


@dataclass
class WeatherReading:
    """One point-in-time weather reading."""

    temperature_f: Optional[float] = None
    humidity_percent: Optional[float] = None
    wind_speed_mph: Optional[float] = None
    wind_direction_degrees: Optional[float] = None  # compass bearing the wind blows TOWARD
    feels_like_f: Optional[float] = None
    rain_percent: Optional[float] = None
    air_density: Optional[float] = None  # kg/m^3, when computable (needs temp+humidity+altitude)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WeatherSnapshot:
    """Weather for one game across four display points, plus
    delay/postponement risk and roof status. Immutable once persisted."""

    game_id: str
    provider_name: str
    is_mock: bool
    retrieved_at: str
    roof_status: str  # "open" | "closed" | "dome" | "unknown"
    delay_risk_percent: Optional[float]
    postponement_risk_percent: Optional[float]
    current: WeatherReading = field(default_factory=WeatherReading)
    first_pitch: WeatherReading = field(default_factory=WeatherReading)
    mid_game: WeatherReading = field(default_factory=WeatherReading)
    late_game: WeatherReading = field(default_factory=WeatherReading)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class WeatherConclusion:
    """One deterministic, structured weather conclusion (never
    free-form LLM text) -- e.g. "Strong wind blowing out to RF"."""

    code: str
    text: str
    favors: str  # "hitter" | "pitcher" | "neutral" | "risk"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WeatherAnalysis:
    game_id: str
    conclusions: List[WeatherConclusion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"game_id": self.game_id, "conclusions": [c.to_dict() for c in self.conclusions]}


# ----------------------------------------------------------------------------
# Vegas
# ----------------------------------------------------------------------------


@dataclass
class VegasLine:
    moneyline: Optional[int] = None
    run_line: Optional[float] = None
    run_line_odds: Optional[int] = None
    total: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VegasSnapshot:
    game_id: str
    home_team: str
    away_team: str
    provider_name: str
    is_mock: bool
    retrieved_at: str
    opening_home: VegasLine
    opening_away: VegasLine
    current_home: VegasLine
    current_away: VegasLine
    home_implied_runs: Optional[float]
    away_implied_runs: Optional[float]
    total_movement: Optional[float]  # current_total - opening_total ("opening" = FIRST OBSERVED by this project, see is_first_pull_of_day
    moneyline_movement_home: Optional[int]  # current - opening, home side

    # --- Milestone 24: real-provider provenance, per-book detail, and ---
    # --- explainable consensus/implied-runs methodology ----------------
    # Every field below is None for MockVegasProvider (mock never reports
    # a real event id, a real book list, or a real calculation method).
    event_id: Optional[str] = None
    books: List["BookLineSnapshot"] = field(default_factory=list)
    books_used: List[str] = field(default_factory=list)
    market_count: int = 0
    consensus_method: Optional[str] = None
    consensus_home_win_probability: Optional[float] = None
    consensus_away_win_probability: Optional[float] = None

    # Implied-runs explainability (research/game_environment/providers/implied_runs.py)
    implied_runs_calculation_method: Optional[str] = None
    implied_runs_input_total: Optional[float] = None
    implied_runs_input_home_run_line: Optional[float] = None
    implied_runs_input_home_moneyline: Optional[int] = None
    implied_runs_input_away_moneyline: Optional[int] = None
    implied_runs_is_valid: bool = True
    validation_warnings: List[str] = field(default_factory=list)

    # "First Observed" honesty (see providers/normalizer.py's module
    # docstring and vegas.py's _resolve_first_observed()): True when
    # THIS pull is the first one seen today for this game, meaning
    # opening_home/opening_away are identical to current_home/current_away
    # by construction, not a real earlier line. Never labeled "opening"
    # (a real sportsbook open) anywhere in this project.
    is_first_pull_of_day: bool = True

    # --- Milestone 25: pregame lock / freeze provenance -----------------
    # `game_status` is the PREGAME/IN_PLAY/FINAL/UNKNOWN classification
    # (research/game_environment/game_status.py) AT THE MOMENT this
    # specific snapshot's underlying market data was captured -- frozen
    # into the snapshot forever, never recomputed later against the
    # game's CURRENT status. `is_frozen_pregame` is True only when this
    # object is an OLDER, already-PREGAME-classified snapshot being
    # reused (unmodified, including its original retrieved_at) because a
    # fresh pregame fetch is no longer possible. `vegas_projection_status`
    # is the dashboard-ready label ("LIVE_PREGAME" | "PREGAME_FROZEN" |
    # "MISSING" | "INVALID" | "IN_PLAY_ONLY") computed once here so the
    # dashboard never has to re-derive it.
    game_status: str = "UNKNOWN"
    is_frozen_pregame: bool = False
    vegas_projection_status: str = "MISSING"

    # --- Milestone 27: multi-provider (SportsGameOdds primary, The Odds
    # API secondary) provenance. `selected_provider` is the human-
    # readable provider name (matches `provider_name`) whose data this
    # snapshot's current_home/current_away/implied runs actually came
    # from -- None when neither provider produced valid data.
    # `fallback_used` is True only when the PRIMARY provider did not
    # produce valid pregame data and the SECONDARY provider's did.
    # `primary_provider_status`/`secondary_provider_status` are one of
    # providers/coverage.py's VALID / NOT_CONFIGURED / ALL_MISSING_REASONS
    # values, always recorded (never left ambiguous) so a "missing" game
    # can always be explained rather than just reported. `missing_reason`
    # is set (from providers/coverage.py's categories) only when NEITHER
    # provider produced valid data -- this project's final, single
    # explanation for why Vegas contribution is zero for this game.
    selected_provider: Optional[str] = None
    fallback_used: bool = False
    primary_provider_status: Optional[str] = None
    secondary_provider_status: Optional[str] = None
    missing_reason: Optional[str] = None

    # Milestone 27.1: True when a provider's own status (e.g.
    # SportsGameOdds saying IN_PLAY/FINAL) was REJECTED by the
    # impossible-state guard (research/game_environment/game_status.py
    # ::game_has_not_started_yet()) because the current moment is still
    # before the authoritative MLB scheduled start -- an "impossible
    # state" that either means the wrong provider event was matched, or
    # the provider itself is stale/wrong. When True, this snapshot's
    # game_status was deliberately kept at PREGAME instead of trusting
    # the provider.
    provider_status_conflict: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class BookLineSnapshot:
    """One sportsbook's line as stored on a VegasSnapshot -- same shape
    as providers/models.py::BookLine, duplicated here (rather than
    imported) so research/game_environment/models.py has no dependency
    on the providers/ subpackage; vegas.py does the conversion."""

    book: str
    home_moneyline: Optional[int] = None
    away_moneyline: Optional[int] = None
    total: Optional[float] = None
    total_over_odds: Optional[int] = None
    total_under_odds: Optional[int] = None
    home_run_line: Optional[float] = None
    away_run_line: Optional[float] = None
    home_run_line_odds: Optional[int] = None
    away_run_line_odds: Optional[int] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VegasSlateAnalysis:
    """Slate-wide Vegas conclusions -- computed once across every game,
    not per-game (see collector.py)."""

    highest_total_game_id: Optional[str] = None
    lowest_total_game_id: Optional[str] = None
    largest_movement_game_id: Optional[str] = None
    biggest_favorite_game_id: Optional[str] = None
    biggest_underdog_game_id: Optional[str] = None
    sharp_movement_game_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# Ballpark (static reference data)
# ----------------------------------------------------------------------------


@dataclass
class BallparkProfile:
    team_abbr: str
    venue_name: str
    hr_factor: int
    run_factor: int
    park_factor: int
    altitude_ft: int
    roof: str  # "open" | "dome" | "retractable"
    surface: str  # "grass" | "turf"
    orientation_degrees: float

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# Umpire
# ----------------------------------------------------------------------------


@dataclass
class UmpireProfile:
    game_id: str
    status: str  # "KNOWN" | "UNKNOWN"
    name: Optional[str] = None
    strike_percent: Optional[float] = None
    walk_percent: Optional[float] = None
    k_percent: Optional[float] = None
    zone_size_score: Optional[float] = None  # 0-100, higher = bigger zone
    runs_per_game: Optional[float] = None
    tendency: str = "unknown"  # "pitcher_friendly" | "hitter_friendly" | "neutral" | "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# Bullpen
# ----------------------------------------------------------------------------


@dataclass
class BullpenProfile:
    team_abbr: str
    provider_name: str
    is_mock: bool
    era: Optional[float] = None
    fip: Optional[float] = None
    xfip: Optional[float] = None
    relievers_used_last_3_days: Optional[int] = None
    estimated_fatigue: str = "unknown"  # "low" | "medium" | "high" | "unknown"
    closer_available: Optional[bool] = None
    high_leverage_arms_available: Optional[int] = None
    strength_score: Optional[float] = None  # 0-100, higher = stronger bullpen (bad for opposing hitters)

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# Travel
# ----------------------------------------------------------------------------


@dataclass
class TravelProfile:
    team_abbr: str
    opponent_abbr: str
    is_home: bool
    status: str  # "KNOWN" | "UNKNOWN"
    distance_miles: Optional[float] = None
    timezones_crossed: Optional[int] = None
    back_to_back: Optional[bool] = None  # None = UNKNOWN (no schedule history available)
    getaway_day: Optional[bool] = None  # None = UNKNOWN

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------
# Scoring + Summary
# ----------------------------------------------------------------------------


@dataclass
class EnvironmentScore:
    overall: float
    pitcher: float
    hitter: float
    stack: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FutureAdjustmentPreview:
    """Disabled, non-functional preview of what a future projection
    adjustment MIGHT look like once this engine feeds the projection
    layer. Never applied to any real projection -- see the milestone's
    explicit "Do NOT modify projections" instruction and
    dashboard-side FutureAdjustmentPreview.tsx, which renders this as
    a visibly disabled card."""

    weather_points: Optional[float] = None
    vegas_points: Optional[float] = None
    bullpen_points: Optional[float] = None
    enabled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GameSummary:
    headline: str
    bullet_points: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GameEnvironmentReport:
    game_id: str
    home_team: str
    away_team: str
    game_datetime_utc: Optional[str]
    venue_name: Optional[str]

    environment_score: EnvironmentScore
    summary: GameSummary
    future_adjustment_preview: FutureAdjustmentPreview

    weather: Optional[WeatherSnapshot] = None
    weather_analysis: Optional[WeatherAnalysis] = None
    vegas: Optional[VegasSnapshot] = None
    ballpark: Optional[BallparkProfile] = None
    umpire: Optional[UmpireProfile] = None
    bullpen_home: Optional[BullpenProfile] = None
    bullpen_away: Optional[BullpenProfile] = None
    travel_home: Optional[TravelProfile] = None
    travel_away: Optional[TravelProfile] = None

    # --- Milestone 25: pregame lock / DK slate coverage ------------------
    # `mlb_game_status` is the RAW MLB Stats API detailedState string
    # (e.g. "Scheduled", "In Progress", "Final") -- already collected by
    # research/collector.py into research_output/<date>/games.json but,
    # before this milestone, never threaded past there. `game_status` is
    # its PREGAME/IN_PLAY/FINAL/UNKNOWN classification (game_status.py).
    # `vegas` (above) is ALWAYS the pregame-safe value Native/AI consume
    # (live pregame, frozen pregame, or None/zero-contribution) -- it is
    # NEVER replaced by in-play odds. `vegas_live` is the CURRENT market
    # snapshot regardless of game status, for research/history display
    # only (the Vegas Intelligence page's LIVE MARKET tab) -- nothing in
    # native_projections/ or projection_engine/ ever reads this field.
    mlb_game_status: Optional[str] = None
    game_status: str = "UNKNOWN"
    vegas_live: Optional[VegasSnapshot] = None

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "game_datetime_utc": self.game_datetime_utc,
            "venue_name": self.venue_name,
            "environment_score": self.environment_score.to_dict(),
            "summary": self.summary.to_dict(),
            "future_adjustment_preview": self.future_adjustment_preview.to_dict(),
            "weather": self.weather.to_dict() if self.weather else None,
            "weather_analysis": self.weather_analysis.to_dict() if self.weather_analysis else None,
            "vegas": self.vegas.to_dict() if self.vegas else None,
            "ballpark": self.ballpark.to_dict() if self.ballpark else None,
            "umpire": self.umpire.to_dict() if self.umpire else None,
            "bullpen_home": self.bullpen_home.to_dict() if self.bullpen_home else None,
            "bullpen_away": self.bullpen_away.to_dict() if self.bullpen_away else None,
            "travel_home": self.travel_home.to_dict() if self.travel_home else None,
            "travel_away": self.travel_away.to_dict() if self.travel_away else None,
            "mlb_game_status": self.mlb_game_status,
            "game_status": self.game_status,
            "vegas_live": self.vegas_live.to_dict() if self.vegas_live else None,
        }


@dataclass
class SlateEnvironmentReport:
    slate_date: str
    generated_at: str
    engine_version: str
    games: List[GameEnvironmentReport] = field(default_factory=list)
    vegas_slate_analysis: Optional[VegasSlateAnalysis] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slate_date": self.slate_date,
            "generated_at": self.generated_at,
            "engine_version": self.engine_version,
            "games": [g.to_dict() for g in self.games],
            "vegas_slate_analysis": self.vegas_slate_analysis.to_dict() if self.vegas_slate_analysis else None,
            "warnings": self.warnings,
        }
