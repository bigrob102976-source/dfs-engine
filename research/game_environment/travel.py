"""Deterministic travel research for the Game Environment Engine
(Milestone DS2).

Distance and timezones-crossed are computed from the static team-
location dataset (config/game_environment_config.py's TEAM_LOCATIONS)
-- real, if approximate, geography, not fetched over the network.
back_to_back and getaway_day genuinely require game-by-game schedule
history this project doesn't collect yet, so those two fields always
report UNKNOWN (None) rather than being guessed -- see the milestone's
explicit "Only if data available. Otherwise UNKNOWN" instruction.
"""

import math
from typing import Optional
from zoneinfo import ZoneInfo

from config.game_environment_config import TEAM_LOCATIONS
from research.game_environment.models import TravelProfile

_EARTH_RADIUS_MILES = 3958.8


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return _EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(a))


def _utc_offset_hours(tz_name: str) -> float:
    """A fixed reference instant is intentionally NOT used here --
    callers only ever compare two offsets computed at the SAME instant
    (see timezones_crossed below), so DST is consistent between them."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    offset = now.astimezone(ZoneInfo(tz_name)).utcoffset()
    return (offset.total_seconds() / 3600.0) if offset is not None else 0.0


def build_travel_profile(team_abbr: str, opponent_abbr: str, is_home: bool) -> TravelProfile:
    """Distance is always FROM the away team's home city TO the game
    site (the home team's park) -- that's the only travel that's
    meaningful for a single game with no prior-game location on record.
    A home team's own profile reports distance_miles=0 (they're not
    traveling) but still an honest KNOWN status."""
    home_team = team_abbr if is_home else opponent_abbr
    home_loc = TEAM_LOCATIONS.get(home_team)
    away_team = opponent_abbr if is_home else team_abbr
    away_loc = TEAM_LOCATIONS.get(away_team)

    if home_loc is None or away_loc is None:
        return TravelProfile(team_abbr=team_abbr, opponent_abbr=opponent_abbr, is_home=is_home, status="UNKNOWN")

    if is_home:
        distance = 0.0
        timezones_crossed = 0
    else:
        distance = round(_haversine_miles(away_loc["lat"], away_loc["lon"], home_loc["lat"], home_loc["lon"]), 1)
        timezones_crossed = round(abs(_utc_offset_hours(home_loc["timezone"]) - _utc_offset_hours(away_loc["timezone"])))

    return TravelProfile(
        team_abbr=team_abbr, opponent_abbr=opponent_abbr, is_home=is_home, status="KNOWN",
        distance_miles=distance, timezones_crossed=timezones_crossed,
        back_to_back=None, getaway_day=None,
    )
