"""Milestone 32.1, Part 1 & 7 -- the canonical MLB regular-season game
universe for Warehouse V1.

Filtering rule (Part 1): MLB Stats API's own `gameType` field on every
schedule entry is "R" for regular season, "S"/"E" for spring training/
exhibition, "A" for the All-Star Game, and a season-specific code for
each postseason round -- filtering to gameType == "R" structurally
excludes spring training, the All-Star Game, and postseason in one
condition (live-confirmed: 'E'/'S'/'R' all observed in a March 2025
schedule query -- see this milestone's report). The Home Run Derby
isn't a scheduled "game" in this endpoint at all, so it never appears.

A game is only INCLUDED if its outcome can be safely represented
(abstractGameState == "Final") -- postponed/suspended/cancelled/
in-progress games are excluded from games.parquet entirely (Part 1:
"games whose final outcomes cannot be represented safely"). A
postponed game that was later replayed gets its own, different gamePk
under MLB's own scheduling convention, so this never loses real games,
only non-outcomes.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from historical_mlb.sources.mlb_stats import fetch_schedule_range


@dataclass
class GameUniverseRow:
    season: int
    game_date: str
    game_pk: int
    game_number: int
    away_team: str
    home_team: str
    away_team_id: int
    home_team_id: int
    venue_id: Optional[int]
    venue_name: Optional[str]
    scheduled_start: Optional[str]
    final_status: str
    double_header: Optional[str]
    away_probable_pitcher_id: Optional[int]
    home_probable_pitcher_id: Optional[int]


def _is_regular_season_final(game: dict) -> bool:
    return game.get("gameType") == "R" and (game.get("status") or {}).get("abstractGameState") == "Final"


def build_game_universe(start_date: str, end_date: str, chunk_days: int = 45) -> List[GameUniverseRow]:
    """Fetches the schedule for [start_date, end_date] in bounded
    chunks (Part 6: keeps any one request's payload/response time
    reasonable over an 18-month range, without falling back to one
    request per day) and returns only regular-season, safely-Final
    games."""
    from datetime import date, timedelta

    y, m, d = (int(x) for x in start_date.split("-"))
    cursor = date(y, m, d)
    y2, m2, d2 = (int(x) for x in end_date.split("-"))
    end = date(y2, m2, d2)

    rows: List[GameUniverseRow] = []
    seen_pks = set()
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        schedule = fetch_schedule_range(cursor.isoformat(), chunk_end.isoformat())
        for date_block in schedule.get("dates", []):
            for game in date_block.get("games", []):
                if not _is_regular_season_final(game):
                    continue
                pk = game.get("gamePk")
                if pk in seen_pks:
                    continue  # a game can appear in more than one date block query result at chunk boundaries -- never duplicated
                seen_pks.add(pk)
                teams = game.get("teams", {})
                away, home = teams.get("away", {}), teams.get("home", {})
                venue = game.get("venue") or {}
                rows.append(GameUniverseRow(
                    season=int(game.get("season") or cursor.year),
                    game_date=game.get("officialDate") or date_block.get("date"),
                    game_pk=pk,
                    game_number=game.get("gameNumber", 1),
                    away_team=(away.get("team") or {}).get("abbreviation") or (away.get("team") or {}).get("name"),
                    home_team=(home.get("team") or {}).get("abbreviation") or (home.get("team") or {}).get("name"),
                    away_team_id=(away.get("team") or {}).get("id"),
                    home_team_id=(home.get("team") or {}).get("id"),
                    venue_id=venue.get("id"),
                    venue_name=venue.get("name"),
                    scheduled_start=game.get("gameDate"),
                    final_status=(game.get("status") or {}).get("detailedState", "Final"),
                    double_header=game.get("doubleHeader"),
                    away_probable_pitcher_id=(away.get("probablePitcher") or {}).get("id"),
                    home_probable_pitcher_id=(home.get("probablePitcher") or {}).get("id"),
                ))
        cursor = chunk_end + timedelta(days=1)
    _repair_ambiguous_double_headers(rows)
    return rows


def _repair_ambiguous_double_headers(rows: List[GameUniverseRow]) -> None:
    """Milestone 32.1 regression guard for a real bug caught live during
    the full warehouse build: MLB Stats API's `gameNumber` (and
    `gameDate`/start time) for a POSTPONEMENT-MAKEUP doubleheader (e.g.
    "Makeup of 4/2 PPD" + "Makeup of 4/3 PPD" both actually played on
    4/4) comes back INCONSISTENT when queried via a wide startDate/
    endDate range -- both games reported gameNumber=1, each apparently
    still carrying its own pre-postponement scheduling metadata rather
    than its true doubleheader-relative number. The SAME query scoped
    to a single day (startDate == endDate == the actual played date)
    reliably returns the correct, distinct 1/2 (confirmed live on
    several real examples -- see this milestone's report). This
    function detects any (game_date, away_team, home_team) group with a
    duplicate game_number and repairs ONLY those specific games via a
    narrow single-day re-query -- not a redesign of the wide-range
    fetch, which is correct for every other game.

    Mutates `rows` in place (GameUniverseRow.game_number/scheduled_start
    on the affected rows only); game_pk, the true canonical identifier,
    is never touched."""
    from collections import defaultdict

    by_matchup: Dict = defaultdict(list)
    for row in rows:
        by_matchup[(row.game_date, row.away_team, row.home_team)].append(row)

    by_pk = {row.game_pk: row for row in rows}
    for (game_date, _away, _home), group in by_matchup.items():
        if len(group) < 2:
            continue
        if len({r.game_number for r in group}) == len(group):
            continue  # already distinct -- a real, unambiguous doubleheader (or an unrelated same-day/date collision this function doesn't need to touch)

        corrected = fetch_schedule_range(game_date, game_date)
        for date_block in corrected.get("dates", []):
            for game in date_block.get("games", []):
                pk = game.get("gamePk")
                if pk in by_pk and by_pk[pk] in group:
                    by_pk[pk].game_number = game.get("gameNumber", by_pk[pk].game_number)
                    by_pk[pk].scheduled_start = game.get("gameDate", by_pk[pk].scheduled_start)


def games_for_date(rows: List[GameUniverseRow], date: str) -> List[GameUniverseRow]:
    return [r for r in rows if r.game_date == date]
