"""Fetches + caches one team's active roster from the real MLB Stats API
(research.collector.fetch_team_roster -- the same, single network-access
module the rest of the Research Engine uses; no new endpoint is
invented here). Live-verified response shape (2026-08-23, team 147):

    {"roster": [
        {"person": {"id": 645305, "fullName": "Ali Sanchez"},
         "position": {"abbreviation": "C"},
         "status": {"code": "A", "description": "Active"}},
        ...
    ]}

Cached per (date, team_id) via research.cache.get_or_fetch -- a roster
is fetched AT MOST ONCE PER TEAM PER REFRESH, never once per player (see
this package's refresh.py for the "one team, once" performance
requirement).
"""

from pathlib import Path
from typing import List, Optional

from research import cache
from research.collector import fetch_team_roster

DEFAULT_ROSTER_CACHE_ROOT = cache.DEFAULT_CACHE_ROOT

# The real roster endpoint reports a plain "P" for every pitcher --
# never "SP"/"RP" (those only appear in DraftKings' own export, see
# dfs/player_resolver.py::PITCHER_DK_POSITIONS). Kept separate from that
# constant: this reflects MLB Stats API's vocabulary, not DraftKings'.
_ROSTER_PITCHER_POSITIONS = frozenset({"P"})


def fetch_cached_team_roster(team_id: str, date: str, cache_root: Path = DEFAULT_ROSTER_CACHE_ROOT) -> Optional[dict]:
    return cache.get_or_fetch(cache_root, date, f"roster_{team_id}", lambda: fetch_team_roster(team_id))


def parse_roster_entries(raw_roster: Optional[dict]) -> List[dict]:
    """Turns the raw MLB Stats API roster payload into a flat list of
    {"mlb_player_id", "name", "position_abbr", "player_type", "active"}
    dicts. Returns [] (never raises) for a None/malformed payload -- one
    team's bad response must never take down the whole refresh."""
    if not raw_roster:
        return []
    entries: List[dict] = []
    for row in raw_roster.get("roster") or []:
        person = row.get("person") or {}
        player_id = person.get("id")
        name = person.get("fullName")
        if player_id is None or not name:
            continue
        position_abbr = (row.get("position") or {}).get("abbreviation")
        status_code = (row.get("status") or {}).get("code")
        entries.append({
            "mlb_player_id": str(player_id),
            "name": name,
            "position_abbr": position_abbr,
            "player_type": "pitcher" if position_abbr in _ROSTER_PITCHER_POSITIONS else "hitter",
            "active": status_code == "A",
        })
    return entries
