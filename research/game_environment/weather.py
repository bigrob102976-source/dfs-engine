"""Weather collection + deterministic analysis for the Game Environment
Engine (Milestone DS2).

IMPORTANT DATA-SOURCE RULE (same discipline as
external_projections/bluecollar_provider.py): a WeatherProvider
implementation must never guess an API endpoint or invent network
behavior.

Milestone 32.6 Part 5: OpenMeteoWeatherProvider below is the REAL, live
provider (Open-Meteo Forecast API, no key required) -- it is the
DEFAULT provider (see collector.py's get_configured_weather_provider())
so production/live slates never use mock weather. MockWeatherProvider
remains available and clearly labeled (is_mock=True) for local dev/
testing only, opted into explicitly via GAME_ENVIRONMENT_PROVIDER=mock.
"""

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from config.game_environment_config import (
    RAIN_DELAY_RISK_HIGH_PERCENT,
    POSTPONEMENT_RISK_HIGH_PERCENT,
    TEAM_LOCATIONS,
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
from research.game_environment.providers.open_meteo import (
    OpenMeteoUnavailableError,
    fetch_forecast,
    game_window_indices,
    nearest_hour_index,
    reading_at,
)
from research.game_environment.weather_risk import compute_weather_risk


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


_INDOOR_READING = WeatherReading(
    temperature_f=72.0, humidity_percent=45.0, wind_speed_mph=0.0, wind_direction_degrees=0.0,
    feels_like_f=72.0, rain_percent=0.0, air_density=1.20,
    precipitation_probability_percent=0.0, precipitation_amount_mm=0.0, weather_code=0, wind_gusts_mph=0.0,
)


class OpenMeteoWeatherProvider(WeatherProvider):
    """Real, keyless live forecast provider (Milestone 32.6 Part 5) --
    see providers/open_meteo.py's module docstring for the exact
    endpoint/params/caching. Uses config.game_environment_config.TEAM_LOCATIONS
    for stadium coordinates -- the existing authoritative home-city
    lat/lon table this project already uses for travel.py; no separate
    venue table is introduced.

    Roof handling: only a CONFIRMED closed dome ("dome"/"closed" in the
    static BALLPARKS roof field) is treated as indoor. A "retractable"
    roof's real-time open/closed state isn't available from any source
    this project has, so it is always treated as open-air -- the
    conservative, honest choice: never hide real weather risk behind a
    guessed "probably closed".

    delay_risk_percent is set to the same value as weather_risk_percent
    (one unified, documented methodology -- see weather_risk.py).
    postponement_risk_percent is left None: this provider has no
    genuine signal distinguishing "risk of any delay" from "risk of a
    full postponement" specifically, and inventing a fraction of the
    other number would violate this project's "never invent missing
    statistics" rule."""

    name = "open_meteo"
    is_mock = False

    def provider_name(self) -> str:
        return "Open-Meteo"

    def is_configured(self) -> bool:
        return True  # keyless API -- always configured

    def get_weather(self, game_id: str, home_team_abbr: str, game_datetime_utc: Optional[str], roof: str) -> WeatherSnapshot:
        if roof in ("dome", "closed"):
            return WeatherSnapshot(
                game_id=game_id, provider_name=self.provider_name(), is_mock=False, retrieved_at=_now(),
                roof_status=roof, delay_risk_percent=0.0, postponement_risk_percent=None,
                current=_INDOOR_READING, first_pitch=_INDOOR_READING, mid_game=_INDOOR_READING, late_game=_INDOOR_READING,
                weather_risk_percent=0.0, weather_status="Indoor game -- no weather risk.",
            )

        location = TEAM_LOCATIONS.get(home_team_abbr)
        if location is None:
            raise WeatherProviderUnavailableError(f"No stadium coordinates configured for {home_team_abbr!r}.")
        if not game_datetime_utc:
            raise WeatherProviderUnavailableError(f"No scheduled start time available for game {game_id} -- cannot select a forecast hour.")

        target = datetime.fromisoformat(game_datetime_utc.replace("Z", "+00:00"))
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        forecast_date = target.date().isoformat()

        try:
            doc = fetch_forecast(home_team_abbr, forecast_date, location["lat"], location["lon"])
        except OpenMeteoUnavailableError as exc:
            raise WeatherProviderUnavailableError(str(exc)) from exc

        hourly = doc.get("hourly", {})
        times = hourly.get("time", [])
        first_pitch_index = nearest_hour_index(times, target)
        if first_pitch_index is None:
            raise WeatherProviderUnavailableError(
                f"Open-Meteo's forecast window doesn't cover the scheduled start ({game_datetime_utc}) for {home_team_abbr}."
            )

        now_index = nearest_hour_index(times, datetime.now(timezone.utc))
        current_index = now_index if now_index is not None else first_pitch_index
        mid_index = min(first_pitch_index + 2, len(times) - 1)
        late_index = min(first_pitch_index + 4, len(times) - 1)

        def _build_reading(index: int) -> WeatherReading:
            r = reading_at(hourly, index)
            temp, humidity, wind_speed = r["temperature_f"], r["humidity_percent"], r["wind_speed_mph"]
            feels_like = None
            if temp is not None:
                feels_like = temp + (5.0 if (humidity is not None and humidity > 70) else 0.0) - (3.0 if (wind_speed is not None and wind_speed > 10) else 0.0)
            return WeatherReading(
                temperature_f=temp, humidity_percent=humidity, wind_speed_mph=wind_speed,
                wind_direction_degrees=r["wind_direction_degrees"], feels_like_f=feels_like,
                rain_percent=r["precipitation_probability"], air_density=None,
                precipitation_probability_percent=r["precipitation_probability"],
                precipitation_amount_mm=r["precipitation"], weather_code=r["weather_code"],
                wind_gusts_mph=r["wind_gusts_mph"],
            )

        window_indices = game_window_indices(times, first_pitch_index, hours_after=4)
        window_readings = [reading_at(hourly, i) for i in window_indices]
        risk_percent, risk_status = compute_weather_risk(window_readings)

        return WeatherSnapshot(
            game_id=game_id, provider_name=self.provider_name(), is_mock=False, retrieved_at=_now(),
            roof_status=roof, delay_risk_percent=risk_percent, postponement_risk_percent=None,
            current=_build_reading(current_index), first_pitch=_build_reading(first_pitch_index),
            mid_game=_build_reading(mid_index), late_game=_build_reading(late_index),
            weather_risk_percent=risk_percent, weather_status=risk_status,
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
