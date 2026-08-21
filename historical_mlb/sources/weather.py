"""Historical weather adapter.

Milestone 32.0 audit finding: no dedicated free historical MLB weather
API was found. Open-Meteo's historical weather archive
(archive-api.open-meteo.com) IS free, requires no API key, and was
live-tested successfully for 2025-06-15 at Comerica Park's coordinates
(temperature/wind speed/wind direction/precipitation/humidity, hourly
granularity, going back decades). This is the same underlying source
several MLB-weather-focused sites (e.g. LineTerminal) are publicly
documented as using.

Reuses this project's OWN existing per-team coordinates
(config/game_environment_config.py::TEAM_LOCATIONS, already built for
the live game-environment pipeline's travel/timezone calculations) as
the join key -- home-team coordinates only (approximates the stadium;
TEAM_LOCATIONS itself documents this as "approximate home-city
coordinates," not exact stadium geocoding). No new coordinate table
was created; this module NEVER redefines TEAM_LOCATIONS.

Caveat (documented honestly, not silently glossed over): home-city
coordinates are not the exact stadium geocode, so wind readings in
particular should be treated as a city-level approximation, not a
field-orientation-aware in-stadium reading -- the existing live weather
pipeline (research/game_environment/) has the SAME limitation today via
its mock provider, so this is not a new gap introduced by this module.
"""

import json
import urllib.parse
import urllib.request
from typing import Optional

from config.game_environment_config import TEAM_LOCATIONS

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_FIELDS = ["temperature_2m", "wind_speed_10m", "wind_direction_10m", "precipitation", "relative_humidity_2m"]


def fetch_historical_weather_json(team_abbr: str, date: str, timeout: int = 20) -> Optional[dict]:
    """One live network call for one team's home coordinates + one date.
    Returns None (never raises) if the team isn't in TEAM_LOCATIONS --
    an unknown abbreviation is a data problem to report, not a crash."""
    location = TEAM_LOCATIONS.get(team_abbr)
    if not location:
        return None
    params = {
        "latitude": location["lat"], "longitude": location["lon"],
        "start_date": date, "end_date": date,
        "hourly": ",".join(HOURLY_FIELDS),
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    }
    url = f"{ARCHIVE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "BigMoneyDFS-Research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def weather_at_hour(payload: Optional[dict], hour_iso: str) -> Optional[dict]:
    """Pure parsing, no network. `hour_iso` like '2025-06-15T18:00' (the
    archive's own hourly time format, local to the requested
    coordinates). Returns None if that exact hour isn't in the payload
    -- never interpolates/guesses a nearby hour silently."""
    if not payload or "hourly" not in payload:
        return None
    hourly = payload["hourly"]
    times = hourly.get("time", [])
    if hour_iso not in times:
        return None
    idx = times.index(hour_iso)
    return {field: hourly.get(field, [None] * len(times))[idx] for field in HOURLY_FIELDS}
