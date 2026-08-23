"""Open-Meteo Forecast API (Milestone 32.6 Part 5) -- the real, live
weather provider. Official docs (source of truth -- nothing here
guesses an undocumented endpoint or field):

    Base URL:  https://api.open-meteo.com/v1/forecast
    Auth:      none required (Open-Meteo's free tier needs no API key)
    Params:    latitude, longitude (stadium coordinates --
               config.game_environment_config.TEAM_LOCATIONS, the
               existing authoritative home-city lat/lon table this
               project already uses for travel.py; not re-collected
               here), hourly=temperature_2m,relative_humidity_2m,
               precipitation_probability,precipitation,weather_code,
               wind_speed_10m,wind_direction_10m,wind_gusts_10m,
               temperature_unit=fahrenheit, wind_speed_unit=mph,
               timezone=UTC (so the returned hourly "time" strings are
               plain UTC ISO8601, directly comparable to
               game_datetime_utc with no timezone-conversion step),
               forecast_days=3 (enough runway for any realistic
               same/next-day MLB start, keeps the response small).

CACHING: research/cache.py's generic get_or_fetch, keyed by
(forecast_date, home_team_abbr) -- one real network call per team per
day regardless of how many games/players/pages touch that team's
weather during a refresh (mirrors historical_mlb/sources/weather.py's
"once per home-team+date" precedent for the same provider's
archive-API sibling, though this hits the separate, keyless forecast
endpoint since a live slate needs a forecast, not history).

FETCH TIMING: called only from the admin-only Refresh Data flow (see
research/game_environment/collector.py's docstring + build_game_report
callers) -- never per-member-page-load (Part 5's explicit requirement).
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from research import cache

API_BASE_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 15
FORECAST_DAYS = 3

HOURLY_VARIABLES = (
    "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,"
    "weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
)

_CACHE_ROOT = cache.DEFAULT_CACHE_ROOT.parent / "open_meteo"


class OpenMeteoUnavailableError(RuntimeError):
    """The Open-Meteo API was reachable but returned an error, a
    malformed body, or an unexpected (non-200) status."""


def _fetch_raw(latitude: float, longitude: float) -> dict:
    url = (
        f"{API_BASE_URL}?latitude={latitude}&longitude={longitude}"
        f"&hourly={HOURLY_VARIABLES}&temperature_unit=fahrenheit&wind_speed_unit=mph"
        f"&timezone=UTC&forecast_days={FORECAST_DAYS}"
    )
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise OpenMeteoUnavailableError(f"Open-Meteo returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise OpenMeteoUnavailableError("Open-Meteo request failed (network error).") from exc

    try:
        data = json.loads(body)
    except ValueError as exc:
        raise OpenMeteoUnavailableError("Open-Meteo returned a malformed (non-JSON) response.") from exc
    if "hourly" not in data:
        raise OpenMeteoUnavailableError("Open-Meteo response is missing the expected 'hourly' block.")
    return data


def fetch_forecast(home_team_abbr: str, forecast_date: str, latitude: float, longitude: float, cache_root: Optional[Path] = None) -> dict:
    """Cached (once per home_team_abbr+forecast_date). `forecast_date`
    is a YYYY-MM-DD cache key, not necessarily "today" -- callers pass
    the slate date being refreshed."""
    root = cache_root if cache_root is not None else _CACHE_ROOT
    return cache.get_or_fetch(root, forecast_date, home_team_abbr, lambda: _fetch_raw(latitude, longitude))


def _parse_hour(iso_no_offset: str) -> datetime:
    # Open-Meteo's timezone=UTC hourly "time" strings are naive
    # (no offset, e.g. "2026-08-23T23:00") -- explicitly UTC per the
    # request param, not the local machine's zone.
    return datetime.fromisoformat(iso_no_offset).replace(tzinfo=timezone.utc)


def nearest_hour_index(hourly_times: List[str], target_utc: datetime) -> Optional[int]:
    """Index of the forecast hour closest to `target_utc`, or None if
    the forecast window doesn't cover it at all (target outside the
    fetched range) -- never guesses/clamps to the nearest edge."""
    if not hourly_times:
        return None
    parsed = [_parse_hour(t) for t in hourly_times]
    best_index, best_delta = None, None
    for i, t in enumerate(parsed):
        delta = abs((t - target_utc).total_seconds())
        if best_delta is None or delta < best_delta:
            best_index, best_delta = i, delta
    # Open-Meteo's hourly cadence is exactly 1 hour -- more than 90
    # minutes off means the target genuinely isn't covered by this
    # forecast window (e.g. a scheduled start well past FORECAST_DAYS).
    if best_delta is not None and best_delta > 90 * 60:
        return None
    return best_index


def reading_at(hourly: dict, index: int) -> Dict[str, Optional[float]]:
    """One hour's values by field, defensively (a field can legitimately
    be absent/None for an hour Open-Meteo didn't model, e.g. right at
    the edge of the forecast window)."""

    def _get(field: str):
        values = hourly.get(field)
        if not isinstance(values, list) or index >= len(values):
            return None
        return values[index]

    return {
        "temperature_f": _get("temperature_2m"),
        "humidity_percent": _get("relative_humidity_2m"),
        "precipitation_probability": _get("precipitation_probability"),
        "precipitation": _get("precipitation"),
        "weather_code": _get("weather_code"),
        "wind_speed_mph": _get("wind_speed_10m"),
        "wind_direction_degrees": _get("wind_direction_10m"),
        "wind_gusts_mph": _get("wind_gusts_10m"),
    }


def game_window_indices(hourly_times: List[str], first_pitch_index: int, hours_after: int = 4) -> List[int]:
    """First-pitch-through-approximately-+hours_after window, clamped to
    whatever the forecast actually covers (never indexes past the end)."""
    last = min(first_pitch_index + hours_after, len(hourly_times) - 1)
    return list(range(first_pitch_index, last + 1))
