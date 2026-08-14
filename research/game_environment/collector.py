"""Assembles ONE game's full Game Environment report from every signal
source, and resolves which providers are configured.

Provider resolution mirrors dfs/providers/config.py's DFS-salary
pattern for weather/vegas/bullpen (GAME_ENVIRONMENT_PROVIDER unset ->
automatic mock fallback, so the engine is useful with zero setup) but
deliberately does NOT auto-fallback umpire data to mock -- the
milestone is explicit that umpire status must be UNKNOWN rather than
guessed unless a provider is genuinely configured (see umpires.py's
module docstring). Set GAME_ENVIRONMENT_UMPIRE_PROVIDER=mock to opt
into the mock umpire provider for testing/demo purposes.
"""

import os
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

from research.game_environment import ballpark, bullpen, summary, travel, umpires, vegas, weather
from research.game_environment.bullpen import BullpenProvider, MockBullpenProvider
from research.game_environment.models import FutureAdjustmentPreview, GameEnvironmentReport
from research.game_environment.scoring import score_environment
from research.game_environment.umpires import MockUmpireProvider, UmpireProvider, UnknownUmpireProvider
from research.game_environment.vegas import MockVegasProvider, VegasProvider
from research.game_environment.weather import MockWeatherProvider, WeatherProvider

WEATHER_PROVIDER_FACTORIES: Dict[str, Callable[[], WeatherProvider]] = {"mock": MockWeatherProvider}
VEGAS_PROVIDER_FACTORIES: Dict[str, Callable[[], VegasProvider]] = {"mock": MockVegasProvider}
BULLPEN_PROVIDER_FACTORIES: Dict[str, Callable[[], BullpenProvider]] = {"mock": MockBullpenProvider}
UMPIRE_PROVIDER_FACTORIES: Dict[str, Callable[[], UmpireProvider]] = {"mock": MockUmpireProvider}

DEFAULT_FALLBACK_KEY = "mock"


def get_configured_weather_provider() -> Tuple[WeatherProvider, str]:
    name = (os.environ.get("GAME_ENVIRONMENT_PROVIDER") or "").strip().lower()
    if not name:
        return WEATHER_PROVIDER_FACTORIES[DEFAULT_FALLBACK_KEY](), "automatic_fallback"
    factory = WEATHER_PROVIDER_FACTORIES.get(name, WEATHER_PROVIDER_FACTORIES[DEFAULT_FALLBACK_KEY])
    return factory(), "explicit"


def get_configured_vegas_provider() -> Tuple[VegasProvider, str]:
    name = (os.environ.get("GAME_ENVIRONMENT_PROVIDER") or "").strip().lower()
    if not name:
        return VEGAS_PROVIDER_FACTORIES[DEFAULT_FALLBACK_KEY](), "automatic_fallback"
    factory = VEGAS_PROVIDER_FACTORIES.get(name, VEGAS_PROVIDER_FACTORIES[DEFAULT_FALLBACK_KEY])
    return factory(), "explicit"


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
) -> GameEnvironmentReport:
    """Collects every signal for one game and scores/summarizes it.
    Never raises for a missing/unavailable individual signal -- a
    provider failure for one game degrades that section to None/UNKNOWN
    rather than failing the whole report (see engine.py, which does the
    same at the slate level)."""
    park = ballpark.get_ballpark_profile(home_team)
    roof = park.roof if park is not None else "open"

    weather_snapshot = weather_provider.get_weather(game_id, home_team, game_datetime_utc, roof) if weather_provider.is_configured() else None
    weather_analysis = weather.analyze_weather(weather_snapshot, park) if weather_snapshot is not None else None

    vegas_snapshot = vegas_provider.get_vegas_line(game_id, home_team, away_team) if vegas_provider.is_configured() else None

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

    return GameEnvironmentReport(
        game_id=game_id, home_team=home_team, away_team=away_team, game_datetime_utc=game_datetime_utc, venue_name=venue_name,
        environment_score=environment_score, summary=game_summary, future_adjustment_preview=future_adjustment_preview,
        weather=weather_snapshot, weather_analysis=weather_analysis, vegas=vegas_snapshot, ballpark=park, umpire=umpire_profile,
        bullpen_home=bullpen_home, bullpen_away=bullpen_away, travel_home=travel_home, travel_away=travel_away,
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
