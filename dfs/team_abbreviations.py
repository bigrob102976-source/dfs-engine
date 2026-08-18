"""Crosswalk between DraftKings team abbreviations and the abbreviations
our Research Engine uses (which follow the MLB Stats API directly -- see
research/collector.py / research/normalizer.py).

Verified mismatches (research_output/*/teams.json abbreviations vs.
DraftKings' commonly used ones): Arizona is "AZ" in our research package
but DraftKings has historically used "ARI"; the Athletics are "ATH" in
our research package (current MLB Stats API franchise code) but older
DraftKings exports use "OAK". Every other team abbreviation observed in
our research package matches DraftKings' convention directly, so this
map only needs to carry the known exceptions -- everything else passes
through unchanged.

This is a deliberately small, explicit, testable table -- NOT fuzzy
matching. If DraftKings ever renames one of these, add the new code here
rather than trying to infer it.
"""

from typing import Optional

DK_TO_RESEARCH_TEAM_ABBR = {
    "ARI": "AZ",
    "OAK": "ATH",
}


def normalize_dk_team_abbr(dk_abbrev: str) -> str:
    """Map a DraftKings team abbreviation onto our research package's
    abbreviation. Unknown/unmapped codes pass through unchanged (most do)."""
    code = (dk_abbrev or "").strip().upper()
    return DK_TO_RESEARCH_TEAM_ABBR.get(code, code)


# Milestone 27 -- The Odds API's official /v4/sports/baseball_mlb/odds
# endpoint identifies teams by full name (e.g. "Los Angeles Dodgers"),
# not an abbreviation. This is static MLB team-identity reference data
# (all 30 current franchises, matching this project's OWN research-
# package abbreviations -- see config/game_environment_config.py's
# BALLPARKS keys, the same set), not a projection or invented statistic.
MLB_FULL_NAME_TO_ABBR = {
    "Arizona Diamondbacks": "AZ",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Oakland Athletics": "ATH",
    "Athletics": "ATH",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "St Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
}


def normalize_full_team_name(full_name: str) -> Optional[str]:
    """Maps a full MLB team name (as returned by The Odds API) onto this
    project's research-package abbreviation. Returns None (never a
    guess) for an unrecognized name -- the caller must then treat the
    event as unmatched rather than silently attaching odds to the wrong
    team."""
    if not full_name:
        return None
    return MLB_FULL_NAME_TO_ABBR.get(full_name.strip())
