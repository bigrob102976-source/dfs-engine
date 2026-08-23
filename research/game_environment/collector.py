"""Assembles ONE game's full Game Environment report from every signal
source, and resolves which providers are configured.

Provider resolution: weather (Milestone 32.6) defaults to the REAL,
keyless Open-Meteo provider when GAME_ENVIRONMENT_PROVIDER is unset --
production/live slates never silently use mock weather; set
GAME_ENVIRONMENT_PROVIDER=mock to opt into mock weather for local dev/
testing. Bullpen still mirrors dfs/providers/config.py's DFS-salary
pattern (GAME_ENVIRONMENT_PROVIDER unset -> automatic mock fallback --
no free real-data equivalent exists for bullpen usage yet). Umpire data
deliberately does NOT auto-fallback to mock at all -- the milestone is
explicit that umpire status must be UNKNOWN rather than guessed unless
a provider is genuinely configured (see umpires.py's module docstring).
Set GAME_ENVIRONMENT_UMPIRE_PROVIDER=mock to opt into the mock umpire
provider for testing/demo purposes.

Milestone 24: Vegas resolution is DIFFERENT from weather/bullpen and
deliberately does NOT default to mock. Real market data (SportsGameOdds)
is used automatically whenever SPORTSGAMEODDS_API_KEY is set; if it
isn't, Vegas is NOT_CONFIGURED (vegas stays None for every game, exactly
like an unconfigured weather/bullpen provider would) UNLESS
GAME_ENVIRONMENT_PROVIDER=mock is explicitly set. This is an intentional
product-behavior difference from weather/bullpen's "useful with zero
setup" default: a Vegas number silently backed by fake data is far more
likely to be trusted and acted on than a missing weather reading, so
this milestone requires an explicit real key OR an explicit mock
opt-in -- never a silent default to mock (see get_configured_vegas_provider()'s
own docstring below for the exact resolution order).
"""

import os
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

from research.game_environment import ballpark, bullpen, game_status as game_status_module, summary, travel, umpires, vegas, weather
from research.game_environment.bullpen import BullpenProvider, MockBullpenProvider
from research.game_environment.models import FutureAdjustmentPreview, GameEnvironmentReport
from research.game_environment.providers.sportsgameodds import SportsGameOddsProvider
from research.game_environment.providers.theoddsapi import TheOddsAPIProvider
from research.game_environment.scoring import score_environment
from research.game_environment.umpires import MockUmpireProvider, UmpireProvider, UnknownUmpireProvider
from research.game_environment.vegas import (
    MockVegasProvider,
    MultiProviderVegasProvider,
    NotConfiguredVegasProvider,
    SportsGameOddsVegasProvider,
    TheOddsAPIVegasProvider,
    VegasProvider,
)
from research.game_environment.weather import MockWeatherProvider, OpenMeteoWeatherProvider, WeatherProvider

WEATHER_PROVIDER_FACTORIES: Dict[str, Callable[[], WeatherProvider]] = {
    "mock": MockWeatherProvider,
    "open_meteo": OpenMeteoWeatherProvider,
}
BULLPEN_PROVIDER_FACTORIES: Dict[str, Callable[[], BullpenProvider]] = {"mock": MockBullpenProvider}
UMPIRE_PROVIDER_FACTORIES: Dict[str, Callable[[], UmpireProvider]] = {"mock": MockUmpireProvider}

DEFAULT_FALLBACK_KEY = "mock"
# Milestone 32.6 Part 5: weather's own automatic default is the REAL,
# keyless Open-Meteo provider -- production/live slates must never use
# mock weather (see weather.py's module docstring). This is deliberately
# a SEPARATE constant from DEFAULT_FALLBACK_KEY above (which stays
# "mock" for bullpen/umpire -- out of this milestone's scope, and those
# providers have no free real-data equivalent to default to). Setting
# GAME_ENVIRONMENT_PROVIDER=mock explicitly still opts back into mock
# weather for local dev/testing.
WEATHER_DEFAULT_KEY = "open_meteo"


def get_configured_weather_provider() -> Tuple[WeatherProvider, str]:
    name = (os.environ.get("GAME_ENVIRONMENT_PROVIDER") or "").strip().lower()
    if not name:
        return WEATHER_PROVIDER_FACTORIES[WEATHER_DEFAULT_KEY](), "automatic_default"
    factory = WEATHER_PROVIDER_FACTORIES.get(name, WEATHER_PROVIDER_FACTORIES[WEATHER_DEFAULT_KEY])
    return factory(), "explicit"


def get_configured_vegas_provider() -> Tuple[VegasProvider, str]:
    """Resolution order (Milestone 24, extended by Milestone 27):

      1. SPORTSGAMEODDS_API_KEY set -> real primary provider, ALWAYS
         wrapped in MultiProviderVegasProvider even when THE_ODDS_API_KEY
         is unset (secondary=None) -- this is what gives every "missing"
         game an honest providers/coverage.py classification
         (EVENT_NOT_MATCHED / PREGAME_NOT_AVAILABLE / etc.) instead of a
         bare "missing" regardless of whether a secondary provider is
         configured. Source is "multi_provider_configured" when THE_ODDS_
         API_KEY is ALSO set (SportsGameOdds primary, The Odds API
         secondary/fallback), else "sportsgameodds_configured" (single
         real provider, but still coverage-classified). Always wins,
         regardless of GAME_ENVIRONMENT_PROVIDER.
      2. Only THE_ODDS_API_KEY set (no SportsGameOdds key) -> The Odds
         API used ALONE as the sole real provider (source
         "theoddsapi_only_configured") -- still never silently mock.
      3. GAME_ENVIRONMENT_PROVIDER=mock explicitly set -> MockVegasProvider,
         source "explicit_mock".
      4. None of the above -> NotConfiguredVegasProvider
         (is_configured()=False, so build_game_report() below never
         calls it), source "not_configured".
    """
    sgo_key = os.environ.get("SPORTSGAMEODDS_API_KEY")
    odds_api_key = os.environ.get("THE_ODDS_API_KEY")

    if sgo_key:
        primary = SportsGameOddsVegasProvider(SportsGameOddsProvider(api_key=sgo_key))
        if odds_api_key:
            secondary = TheOddsAPIVegasProvider(TheOddsAPIProvider(api_key=odds_api_key))
            return MultiProviderVegasProvider(primary, secondary), "multi_provider_configured"
        return MultiProviderVegasProvider(primary, None), "sportsgameodds_configured"

    if odds_api_key:
        solo = TheOddsAPIVegasProvider(TheOddsAPIProvider(api_key=odds_api_key))
        return MultiProviderVegasProvider(solo, None), "theoddsapi_only_configured"

    explicit = (os.environ.get("GAME_ENVIRONMENT_PROVIDER") or "").strip().lower()
    if explicit == "mock":
        return MockVegasProvider(), "explicit_mock"

    return NotConfiguredVegasProvider(), "not_configured"


def get_configured_bullpen_provider() -> Tuple[BullpenProvider, str]:
    name = (os.environ.get("GAME_ENVIRONMENT_PROVIDER") or "").strip().lower()
    if not name:
        return BULLPEN_PROVIDER_FACTORIES[DEFAULT_FALLBACK_KEY](), "automatic_fallback"
    factory = BULLPEN_PROVIDER_FACTORIES.get(name, BULLPEN_PROVIDER_FACTORIES[DEFAULT_FALLBACK_KEY])
    return factory(), "explicit"


def get_configured_umpire_provider() -> Tuple[UmpireProvider, str]:
    """No automatic mock fallback -- see module docstring. Unset ->
    UnknownUmpireProvider (an honest UNKNOWN for every game)."""
    name = (os.environ.get("GAME_ENVIRONMENT_UMPIRE_PROVIDER") or "").strip().lower()
    if not name:
        return UnknownUmpireProvider(), "unconfigured"
    factory = UMPIRE_PROVIDER_FACTORIES.get(name)
    if factory is None:
        return UnknownUmpireProvider(), "unconfigured"
    return factory(), "explicit"


def build_game_report(
    game_id: str,
    home_team: str,
    away_team: str,
    game_datetime_utc: Optional[str],
    venue_name: Optional[str],
    weather_provider: WeatherProvider,
    vegas_provider: VegasProvider,
    umpire_provider: UmpireProvider,
    bullpen_provider: BullpenProvider,
    slate_date: Optional[str] = None,
    mlb_game_status: Optional[str] = None,
) -> GameEnvironmentReport:
    """Collects every signal for one game and scores/summarizes it.
    Never raises for a missing/unavailable individual signal -- a
    provider failure for one game degrades that section to None/UNKNOWN
    rather than failing the whole report (see engine.py, which does the
    same at the slate level). `slate_date` is passed through to
    vegas_provider.get_vegas_line() (Milestone 24) so a real provider
    fetches the RIGHT day's odds rather than assuming "now"; harmless
    when None (MockVegasProvider ignores it). `mlb_game_status`
    (Milestone 25) is the RAW MLB Stats API detailedState string for
    this game (research_output/<date>/games.json's "status" field,
    already collected -- see engine.py) -- passed through so the Vegas
    provider can classify PREGAME/IN_PLAY/FINAL/UNKNOWN and freeze
    accordingly; harmless when None (every provider treats it the same
    as "authoritative status unavailable")."""
    park = ballpark.get_ballpark_profile(home_team)
    roof = park.roof if park is not None else "open"

    weather_snapshot = weather_provider.get_weather(game_id, home_team, game_datetime_utc, roof) if weather_provider.is_configured() else None
    weather_analysis = weather.analyze_weather(weather_snapshot, park) if weather_snapshot is not None else None

    vegas_snapshot = None
    vegas_live_snapshot = None
    if vegas_provider.is_configured():
        try:
            vegas_snapshot = vegas_provider.get_vegas_line(
                game_id, home_team, away_team, slate_date=slate_date, mlb_game_status=mlb_game_status,
                mlb_scheduled_start_utc=game_datetime_utc,
            )
        except (vegas.VegasProviderUnavailableError, vegas.VegasProviderNotConfiguredError):
            vegas_snapshot = None

        # Milestone 25: best-effort ONLY -- get_live_vegas_line() is not
        # part of the abstract VegasProvider interface (MockVegasProvider/
        # NotConfiguredVegasProvider don't define it), and a failure here
        # must never affect vegas_snapshot (the projection-facing value)
        # above, which is already resolved.
        live_getter = getattr(vegas_provider, "get_live_vegas_line", None)
        if live_getter is not None:
            try:
                vegas_live_snapshot = live_getter(
                    game_id, home_team, away_team, slate_date=slate_date, mlb_game_status=mlb_game_status,
                    mlb_scheduled_start_utc=game_datetime_utc,
                )
            except (vegas.VegasProviderUnavailableError, vegas.VegasProviderNotConfiguredError):
                vegas_live_snapshot = None

    umpire_profile = umpire_provider.get_umpire(game_id)

    bullpen_home = bullpen_provider.get_bullpen(home_team) if bullpen_provider.is_configured() else None
    bullpen_away = bullpen_provider.get_bullpen(away_team) if bullpen_provider.is_configured() else None

    travel_home = travel.build_travel_profile(home_team, away_team, is_home=True)
    travel_away = travel.build_travel_profile(away_team, home_team, is_home=False)

    environment_score = score_environment(park, weather_analysis, vegas_snapshot, bullpen_home, bullpen_away)
    game_summary = summary.generate_game_summary(home_team, away_team, environment_score, weather_analysis, vegas_snapshot, park, bullpen_home, bullpen_away)

    future_adjustment_preview = FutureAdjustmentPreview(
        weather_points=round((environment_score.hitter - 50.0) / 100.0, 2) if weather_analysis is not None else None,
        vegas_points=round((environment_score.stack - 50.0) / 150.0, 2) if vegas_snapshot is not None else None,
        bullpen_points=round((environment_score.hitter - 50.0) / 200.0, 2) if (bullpen_home or bullpen_away) else None,
        enabled=False,
    )

    # Milestone 25: prefer vegas_live_snapshot's classification (it's
    # ALWAYS the current fetch's own status, cross-checked against
    # SportsGameOdds -- see game_status.resolve_game_status()) over a
    # bare MLB-only classification. A FROZEN vegas_snapshot's own
    # game_status field would still read "PREGAME" from whenever it was
    # originally captured, so it must never be used here -- only
    # vegas_live_snapshot (never frozen) reflects the CURRENT status.
    resolved_game_status = vegas_live_snapshot.game_status if vegas_live_snapshot is not None else game_status_module.classify_mlb_game_status(mlb_game_status)

    return GameEnvironmentReport(
        game_id=game_id, home_team=home_team, away_team=away_team, game_datetime_utc=game_datetime_utc, venue_name=venue_name,
        environment_score=environment_score, summary=game_summary, future_adjustment_preview=future_adjustment_preview,
        weather=weather_snapshot, weather_analysis=weather_analysis, vegas=vegas_snapshot, ballpark=park, umpire=umpire_profile,
        bullpen_home=bullpen_home, bullpen_away=bullpen_away, travel_home=travel_home, travel_away=travel_away,
        mlb_game_status=mlb_game_status,
        game_status=resolved_game_status,
        vegas_live=vegas_live_snapshot,
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
