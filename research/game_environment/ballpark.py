"""Static ballpark reference lookup for the Game Environment Engine
(Milestone DS2).

Deliberately NOT a live network call on every refresh -- HR factor, run
factor, altitude, roof, and surface change at most once a year (a new
park, a renovation), so treating them as a versioned static dataset
(config/game_environment_config.py's BALLPARKS) is simpler and more
honest than re-fetching them every slate. See that config module's
docstring for sourcing notes.
"""

from typing import Optional

from config.game_environment_config import BALLPARKS
from research.game_environment.models import BallparkProfile


def get_ballpark_profile(home_team_abbr: str) -> Optional[BallparkProfile]:
    """Returns the HOME team's ballpark profile, or None if the
    abbreviation isn't in the static dataset -- never guesses a
    replacement park's factors."""
    data = BALLPARKS.get(home_team_abbr)
    if data is None:
        return None
    return BallparkProfile(
        team_abbr=home_team_abbr,
        venue_name=data["venue_name"],
        hr_factor=data["hr_factor"],
        run_factor=data["run_factor"],
        park_factor=data["park_factor"],
        altitude_ft=data["altitude_ft"],
        roof=data["roof"],
        surface=data["surface"],
        orientation_degrees=data["orientation_degrees"],
    )
