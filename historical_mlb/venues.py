"""Milestone 32.1, Part 19 -- static venue crosswalk.

Reuses this project's OWN existing config (config/game_environment_config.py's
TEAM_LOCATIONS for lat/lon and BALLPARKS for venue_name/roof) rather
than inventing a new coordinate table -- both are keyed by TEAM
abbreviation, not MLB's own venue_id, so this module derives a
venue_id -> home_team mapping from the ALREADY-COLLECTED game universe
(each game row already carries both venue_id and home_team) and joins
through that. A venue used by more than one "home" team across the
build window (e.g. Sutter Health Park hosting the Athletics) resolves
to whichever team played the most home games there in the collected
window -- documented, not silently arbitrary.

Never invents park factors here (Part 19: "Do not invent park
factors" -- park_factor is intentionally left null on every row this
module produces; BALLPARKS' own hr_factor/run_factor/park_factor
numbers are NOT copied in, since those are today's static approximate
values, not a leakage-safe historical calculation)."""

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from config.game_environment_config import BALLPARKS, TEAM_LOCATIONS


@dataclass
class VenueRow:
    venue_id: int
    venue_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    roof_type: Optional[str] = None
    primary_team: Optional[str] = None
    park_factor: Optional[float] = None  # always None in V1 -- see module docstring


def build_venue_crosswalk(games) -> List[VenueRow]:
    """`games` -- an iterable of historical_mlb.game_universe.GameUniverseRow.
    One row per distinct venue_id actually seen in the collected games."""
    by_venue: Dict[int, Counter] = {}
    venue_names: Dict[int, str] = {}
    for g in games:
        if g.venue_id is None:
            continue
        by_venue.setdefault(g.venue_id, Counter())[g.home_team] += 1
        venue_names[g.venue_id] = g.venue_name or venue_names.get(g.venue_id)

    rows = []
    for venue_id, team_counts in by_venue.items():
        primary_team = team_counts.most_common(1)[0][0] if team_counts else None
        location = TEAM_LOCATIONS.get(primary_team) if primary_team else None
        ballpark = BALLPARKS.get(primary_team) if primary_team else None
        rows.append(VenueRow(
            venue_id=venue_id,
            venue_name=venue_names.get(venue_id) or (ballpark or {}).get("venue_name") or "",
            latitude=location.get("lat") if location else None,
            longitude=location.get("lon") if location else None,
            roof_type=(ballpark or {}).get("roof"),
            primary_team=primary_team,
            park_factor=None,
        ))
    return rows
