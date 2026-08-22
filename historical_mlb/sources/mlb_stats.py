"""MLB Stats API adapter for historical data collection.

Milestone 32.0 audit finding: this project already has a working,
unauthenticated MLB Stats API client (research/collector.py,
evaluation/results_collector.py) used for the LIVE pregame/postgame
pipeline. Historical dates use the exact same endpoints -- MLB Stats API
has no separate "historical" mode, no API key, and no documented rate
limit that was hit during this audit's live testing (3 historical dates
across 2024-2025, ~40 requests total, zero errors/throttling).

This module NEVER redefines those endpoints -- it re-exports the
existing fetch_schedule/fetch_person/fetch_boxscore functions verbatim
(single source of truth for the live pipeline and historical warehouse
alike) and adds only what the live pipeline genuinely doesn't need:
walking EVERY player in a boxscore (the live pipeline only ever looks up
one specific expected player at a time -- see
evaluation/hitter_results_enrichment.py's own docstring), which the
historical warehouse needs to build a complete game's worth of rows.
"""

import json
from typing import Dict, List, Optional, Tuple

from evaluation.results_collector import fetch_boxscore
from research.collector import (
    MLB_STATS_BASE,
    fetch_batter_game_log,
    fetch_person,
    fetch_pitcher_game_log,
    fetch_schedule,
)

from historical_mlb.cache import RawCache
from historical_mlb.http import fetch_url
from historical_mlb.paths import RAW_MLB_DIR

__all__ = [
    "MLB_STATS_BASE",
    "fetch_schedule",
    "fetch_person",
    "fetch_boxscore",
    "fetch_pitcher_game_log",
    "fetch_batter_game_log",
    "extract_all_boxscore_players",
    "games_from_schedule",
    "fetch_schedule_range",
    "fetch_cached_person",
    "fetch_cached_boxscore",
    "fetch_cached_season_game_log",
]

_cache = RawCache(RAW_MLB_DIR)


def fetch_schedule_range(start_date: str, end_date: str) -> dict:
    """Milestone 32.1, Part 6: ONE call covers an entire date range
    (MLB Stats API's own startDate/endDate params, live-confirmed to
    work) instead of one call per day -- the single biggest request-
    count reduction available for building the game universe over 18
    months. Uses the shared retry/backoff helper (this is a NEW call
    this package owns, unlike fetch_schedule() above)."""
    url = f"{MLB_STATS_BASE}/schedule?sportId=1&startDate={start_date}&endDate={end_date}&hydrate=team,probablePitcher,venue"
    return json.loads(fetch_url(url))


def fetch_cached_person(player_id: str, force: bool = False) -> Optional[dict]:
    """Cached wrapper around fetch_person() -- a player's bio/handedness
    never changes retroactively for historical purposes, so this is
    fetched at most once ever per player, not once per game. Uses
    RawCache.get_or_fetch_json, which self-heals a corrupted cache
    entry rather than crashing -- see that method's docstring."""
    key = f"person_{player_id}"
    return _cache.get_or_fetch_json(
        key, fetch_fn=lambda: fetch_person(player_id),
        meta={"source": "mlb_stats_api", "endpoint": "people", "player_id": player_id}, force=force,
    )


def fetch_cached_boxscore(game_pk, force: bool = False) -> Optional[dict]:
    key = f"boxscore_{game_pk}"
    return _cache.get_or_fetch_json(
        key, fetch_fn=lambda: fetch_boxscore(game_pk),
        meta={"source": "mlb_stats_api", "endpoint": "game/boxscore", "game_pk": game_pk}, force=force,
    )


def fetch_cached_season_game_log(player_id: str, season: str, group: str, force: bool = False) -> List[dict]:
    """Milestone 32.1's key scalability decision: fetch a player's
    FULL-SEASON game log ONCE (cached), then every game's rolling
    window is computed by slicing this same cached list by date --
    never a fresh per-game-per-player fetch (M32.0's POC did that,
    which does not scale past ~75 players; a 150-game full-season
    player would otherwise need 150 near-identical fetches instead of
    one). `group` is "pitching" or "hitting". Returns a flat list of
    {"date": ..., "stat": {...}} entries (empty list, never None, on a
    genuine no-data response -- a player with zero games this season is
    a valid, cacheable outcome, not a failure)."""
    key = f"gamelog_{group}_{player_id}_{season}"

    def _fetch() -> List[dict]:
        fetch_fn = fetch_pitcher_game_log if group == "pitching" else fetch_batter_game_log
        raw = fetch_fn(player_id, season)
        splits = (raw or {}).get("stats", [{}])[0].get("splits", []) if raw else []
        return [{"date": s.get("date"), "stat": s.get("stat", {})} for s in splits if s.get("date")]

    entries = _cache.get_or_fetch_json(
        key, fetch_fn=_fetch,
        meta={"source": "mlb_stats_api", "endpoint": f"people/stats(gameLog,{group})", "player_id": player_id, "season": season},
        force=force,
    )
    return entries or []


def games_from_schedule(schedule: dict) -> List[dict]:
    """Flattens MLB Stats API's schedule response (dates -> games) into a
    flat list of one dict per game, each carrying the fields this
    package's game crosswalk needs (Part 5): gamePk, date, teams,
    status, venue, game number (doubleheader-safe)."""
    games: List[dict] = []
    for date_block in schedule.get("dates", []):
        game_date = date_block.get("date")
        for game in date_block.get("games", []):
            teams = game.get("teams", {})
            games.append({
                "game_pk": game.get("gamePk"),
                "game_date": game_date,
                "game_number": game.get("gameNumber", 1),  # 1 or 2 for doubleheaders
                "double_header": game.get("doubleHeader"),  # "Y" | "N" | "S" (split)
                "status": (game.get("status") or {}).get("detailedState"),
                "away_team": (teams.get("away", {}).get("team") or {}).get("name"),
                "away_team_id": (teams.get("away", {}).get("team") or {}).get("id"),
                "home_team": (teams.get("home", {}).get("team") or {}).get("name"),
                "home_team_id": (teams.get("home", {}).get("team") or {}).get("id"),
                "away_probable_pitcher": (teams.get("away", {}).get("probablePitcher") or {}).get("fullName"),
                "away_probable_pitcher_id": (teams.get("away", {}).get("probablePitcher") or {}).get("id"),
                "home_probable_pitcher": (teams.get("home", {}).get("probablePitcher") or {}).get("fullName"),
                "home_probable_pitcher_id": (teams.get("home", {}).get("probablePitcher") or {}).get("id"),
                "venue": (game.get("venue") or {}).get("name"),
            })
    return games


def extract_all_boxscore_players(boxscore: dict) -> Tuple[List[dict], List[dict]]:
    """Walks BOTH teams' player lists in a raw MLB Stats API boxscore
    payload and returns (pitchers, hitters) -- one dict per player who
    actually has a pitching/batting stat block for this game (a two-way
    player can appear in both lists, honestly, rather than being forced
    into one). Each dict carries player_id, name, team_abbr, side
    ("home"/"away"), and the raw stat sub-dict verbatim (untouched --
    scoring.py is the only place that interprets these fields)."""
    pitchers: List[dict] = []
    hitters: List[dict] = []
    for side in ("home", "away"):
        team_block = (boxscore.get("teams") or {}).get(side) or {}
        team_abbr = (team_block.get("team") or {}).get("abbreviation")
        for key, player in (team_block.get("players") or {}).items():
            if not key.startswith("ID"):
                continue
            player_id = key[2:]
            name = (player.get("person") or {}).get("fullName")
            stats = player.get("stats") or {}
            pitching = stats.get("pitching")
            batting = stats.get("batting")
            if pitching:
                pitchers.append({"player_id": player_id, "name": name, "team": team_abbr, "side": side, "stat": pitching})
            if batting:
                hitters.append({"player_id": player_id, "name": name, "team": team_abbr, "side": side, "stat": batting})
    return pitchers, hitters


def person_handedness(person: Optional[dict]) -> Dict[str, Optional[str]]:
    """Extracts bat/throw handedness + primary position from a
    fetch_person() result. NOTE: research.collector.fetch_person()
    already unwraps MLB Stats API's `{"people": [...]}` envelope and
    returns the single flat person dict (or None on failure) -- this
    function takes that same already-unwrapped shape, not the raw API
    envelope. Returns Nones (never guessed) for any field the person
    endpoint didn't actually provide."""
    if not person:
        return {"bat_side": None, "throw_hand": None, "primary_position": None}
    return {
        "bat_side": (person.get("batSide") or {}).get("code"),
        "throw_hand": (person.get("pitchHand") or {}).get("code"),
        "primary_position": (person.get("primaryPosition") or {}).get("abbreviation"),
    }
