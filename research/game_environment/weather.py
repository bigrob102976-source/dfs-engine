"""Weather collection + deterministic analysis for the Game Environment
Engine (Milestone DS2).

IMPORTANT DATA-SOURCE RULE (same discipline as
external_projections/bluecollar_provider.py): a WeatherProvider
implementation must never guess an API endpoint or invent network
behavior. No real weather API is configured or credentialed in this
environment -- only the clearly-labeled MockWeatherProvider is
registered (see research/game_environment/collector.py's registry).
Wiring up a real provider later is a small, contained change: implement
get_weather() against a documented, credentialed weather API.
"""

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from config.game_environment_config import (
    RAIN_DELAY_RISK_HIGH_PERCENT,
    POSTPONEMENT_RISK_HIGH_PERCENT,
    TEMP_COLD_F,
    TEMP_HOT_F,
    WIND_DIRECTION_TOLERANCE_DEGREES,
    WIND_NOTABLE_MPH,
    WIND_STRONG_MPH,
)
from research.game_environment.models import (
    BallparkProfile,
    WeatherAnalysis,
    WeatherConclusion,
    WeatherReading,
    WeatherSnapshot,
)


class WeatherProviderNotConfiguredError(RuntimeError):
    """No real weather provider is configured -- a normal, expected
    state today, not a failure."""


class WeatherProviderUnavailableError(RuntimeError):
    """The provider is configured but unreachable/erroring."""


class WeatherProvider(ABC):
    name: str = "unnamed_provider"
    is_mock: bool = False

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_weather(self, game_id: str, home_team_abbr: str, game_datetime_utc: Optional[str], roof: str) -> WeatherSnapshot:
        """Returns a full four-point weather snapshot for one game.
        `roof` ("open" | "dome" | "retractable") comes from
        ballpark.py's static data -- a closed/dome park always reports
        stable indoor conditions regardless of what's outside."""
        raise NotImplementedError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seeded_fraction(seed: str) -> float:
    """Deterministic pseudo-random value in [0, 1) from a string seed --
    same technique as external_projections/mock_provider.py's
    _mock_multiplier, so re-running produces identical mock weather."""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


class MockWeatherProvider(WeatherProvider):
    """Development/mock weather provider -- see module docstring.
    Deterministic per game_id, clearly labeled, never presented as a
    real forecast."""

    name = "mock_weather_provider"
    is_mock = True

    def provider_name(self) -> str:
        return "MOCK WEATHER"

    def is_configured(self) -> bool:
        return True

    def _reading_for(self, game_id: str, label: str, indoor: bool) -> WeatherReading:
        if indoor:
            return WeatherReading(temperature_f=72.0, humidity_percent=45.0, wind_speed_mph=0.0, wind_direction_degrees=0.0, feels_like_f=72.0, rain_percent=0.0, air_density=1.20)

        frac = _seeded_fraction(f"{game_id}-{label}")
        temp = 55.0 + frac * 45.0  # 55-100F
        humidity = 30.0 + _seeded_fraction(f"{game_id}-{label}-humidity") * 60.0  # 30-90%
        wind_speed = _seeded_fraction(f"{game_id}-{label}-wind") * 20.0  # 0-20mph
        wind_direction = _seeded_fraction(f"{game_id}-{label}-dir") * 360.0
        rain = _seeded_fraction(f"{game_id}-{label}-rain") * 40.0  # 0-40%
        feels_like = temp + (5.0 if humidity > 70 else 0.0) - (3.0 if wind_speed > 10 else 0.0)
        # Simplified ideal-gas approximation -- illustrative, not
        # meteorologically precise; good enough for a relative signal.
        air_density = round(1.225 * (518.7 / (temp + 459.7)), 3)

        return WeatherReading(
            temperature_f=round(temp, 1), humidity_percent=round(humidity, 1), wind_speed_mph=round(wind_speed, 1),
            wind_direction_degrees=round(wind_direction, 0), feels_like_f=round(feels_like, 1), rain_percent=round(rain, 1),
            air_density=air_density,
        )

    def get_weather(self, game_id: str, home_team_abbr: str, game_datetime_utc: Optional[str], roof: str) -> WeatherSnapshot:
        indoor = roof in ("dome", "closed")
        roof_status = "closed" if roof == "retractable" and _seeded_fraction(f"{game_id}-roof") < 0.3 else roof
        indoor = indoor or roof_status == "closed"

        delay_risk = 0.0 if indoor else round(_seeded_fraction(f"{game_id}-delay") * 40.0, 1)
        postponement_risk = 0.0 if indoor else round(_seeded_fraction(f"{game_id}-postpone") * 15.0, 1)

        return WeatherSnapshot(
            game_id=game_id, provider_name=self.provider_name(), is_mock=True, retrieved_at=_now(),
            roof_status=roof_status, delay_risk_percent=delay_risk, postponement_risk_percent=postponement_risk,
            current=self._reading_for(game_id, "current", indoor),
            first_pitch=self._reading_for(game_id, "first_pitch", indoor),
            mid_game=self._reading_for(game_id, "mid_game", indoor),
            late_game=self._reading_for(game_id, "late_game", indoor),
        )


def _wind_relative_to_park(wind_direction_degrees: float, orientation_degrees: float) -> str:
    """"out" if the wind blows toward the park's CF orientation,
    "in" if toward home plate (opposite bearing), else "cross"."""
    diff = abs((wind_direction_degrees - orientation_degrees + 180) % 360 - 180)
    if diff <= WIND_DIRECTION_TOLERANCE_DEGREES:
        return "out"
    if diff >= 180 - WIND_DIRECTION_TOLERANCE_DEGREES:
        return "in"
    return "cross"


def analyze_weather(snapshot: WeatherSnapshot, ballpark: Optional[BallparkProfile]) -> WeatherAnalysis:
    """Deterministic, structured weather conclusions -- every rule reads
    a threshold from config/game_environment_config.py. No free-form
    text generation."""
    conclusions: List[WeatherConclusion] = []

    if snapshot.roof_status in ("dome", "closed"):
        conclusions.append(WeatherConclusion(code="indoor_game", text="Indoor game -- weather is not a factor.", favors="neutral"))
        return WeatherAnalysis(game_id=snapshot.game_id, conclusions=conclusions)

    reading = snapshot.current

    if reading.wind_speed_mph is not None and ballpark is not None and reading.wind_direction_degrees is not None:
        relative = _wind_relative_to_park(reading.wind_direction_degrees, ballpark.orientation_degrees)
        if reading.wind_speed_mph >= WIND_STRONG_MPH:
            if relative == "out":
                conclusions.append(WeatherConclusion(code="wind_strong_out", text="Strong wind blowing out.", favors="hitter"))
            elif relative == "in":
                conclusions.append(WeatherConclusion(code="wind_strong_in", text="Strong wind blowing in.", favors="pitcher"))
            else:
                conclusions.append(WeatherConclusion(code="wind_strong_cross", text="Strong crosswind.", favors="neutral"))
        elif reading.wind_speed_mph >= WIND_NOTABLE_MPH:
            if relative == "out":
                conclusions.append(WeatherConclusion(code="wind_notable_out", text="Notable wind blowing out.", favors="hitter"))
            elif relative == "in":
                conclusions.append(WeatherConclusion(code="wind_notable_in", text="Notable wind blowing in.", favors="pitcher"))

    if reading.temperature_f is not None:
        if reading.temperature_f >= TEMP_HOT_F:
            conclusions.append(WeatherConclusion(code="hot_weather", text="Hot weather favors offense.", favors="hitter"))
        elif reading.temperature_f <= TEMP_COLD_F:
            conclusions.append(WeatherConclusion(code="cold_weather", text="Cold weather suppresses offense.", favors="pitcher"))

    if snapshot.delay_risk_percent is not None and snapshot.delay_risk_percent >= RAIN_DELAY_RISK_HIGH_PERCENT:
        conclusions.append(WeatherConclusion(code="rain_delay_risk", text="High rain delay risk.", favors="risk"))

    if snapshot.postponement_risk_percent is not None and snapshot.postponement_risk_percent >= POSTPONEMENT_RISK_HIGH_PERCENT:
        conclusions.append(WeatherConclusion(code="postponement_risk", text="High postponement risk.", favors="risk"))

    return WeatherAnalysis(game_id=snapshot.game_id, conclusions=conclusions)
