"""Normalizes ONE raw SportsGameOdds v2 `/events` event object into a
provider-agnostic NormalizedGameOdds (providers/models.py).

Market classification is confirmed against a REAL live SportsGameOdds
v2 response (Milestone 24 live validation, 2026-08-17) rather than
guessed. Each entry in an event's `odds` dict is a "betting outcome"
object with (among others) these fields, which is what this module
actually keys off of:

    statID          "points" for the game/team run markets this module
                     collects -- also covers unrelated per-player prop
                     markets ("batting_hits", "batting_homeRuns", ...)
                     that must be excluded.
    betTypeID        "ml" (moneyline), "sp" (spread/run line), "ou"
                     (over/under) -- but also "ml3way", "yn", "eo" for
                     unrelated markets that must be excluded.
    periodID         "game" for the full-game line this module wants --
                     also covers inning-level and first-half props
                     ("1i", "5i", "1h", ...) that must be excluded.
    statEntityID     "all" for the game total, "home"/"away" for
                     moneyline, spread, and TEAM run totals -- also
                     covers "firstToScore"/"lastToScore" (statID
                     differs, so already excluded by the statID check)
                     and individual player IDs for player props.

A naive oddID substring match (e.g. "contains -ou-") is NOT sufficient
on its own: it also matches team-level run totals
("points-away-game-ou-over", marketName "<Team> Runs Over/Under") and
player prop totals, which would silently corrupt the game total with
whichever one iterates last. This module instead requires the full
(statID, betTypeID, periodID, statEntityID) combination below, which is
exact rather than fuzzy.

Team abbreviations are mapped through dfs/team_abbreviations.py's
existing DK<->research crosswalk so a SportsGameOdds abbreviation lines
up with the SAME team codes every other part of this project already
uses (game_environment_config.py's BALLPARKS keys, research package
team abbreviations, etc.) -- never a second, competing abbreviation
scheme.
"""

from typing import Any, Dict, List, Optional

from dfs.team_abbreviations import normalize_dk_team_abbr
from research.game_environment.providers.models import BookLine, NormalizedGameOdds

_GAME_PERIOD = "game"
_POINTS_STAT = "points"


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _team_abbreviation(team_obj: Optional[dict]) -> Optional[str]:
    if not isinstance(team_obj, dict):
        return None
    names = team_obj.get("names") if isinstance(team_obj.get("names"), dict) else {}
    candidate = _first_present(
        {**names, **team_obj},
        ["abbreviation", "short", "abbr", "code", "teamID"],
    )
    if candidate is None:
        return None
    return normalize_dk_team_abbr(str(candidate))


def _iter_book_entries(odd_obj: dict) -> List[Dict[str, Any]]:
    """Each odd object carries a per-bookmaker breakdown under
    `byBookmaker` (confirmed live) -- a couple of other plausible key
    names are tried defensively in case the shape ever differs. Entries
    explicitly marked `available: false` by the provider itself (a
    stale/inactive quote) are skipped rather than fed into consensus."""
    per_book = _first_present(odd_obj, ["byBookmaker", "bookOdds", "books", "bookmakers"])
    if not isinstance(per_book, dict):
        return []
    entries = []
    for book_name, book_data in per_book.items():
        if not isinstance(book_data, dict):
            continue
        if book_data.get("available") is False:
            continue
        entries.append({"book": str(book_name), **book_data})
    return entries


def _classify_market(odd_obj: dict) -> Optional[str]:
    """Returns "ml" / "sp" / "ou" for the full-game moneyline / run line
    / total market this module collects, or None for anything else
    (inning props, player props, 3-way lines, first/last-to-score,
    yes/no markets, etc.) -- see this module's docstring for exactly
    which real SportsGameOdds fields this checks and why a bare oddID
    substring match isn't reliable."""
    if odd_obj.get("statID") != _POINTS_STAT or odd_obj.get("periodID") != _GAME_PERIOD:
        return None
    bet_type = odd_obj.get("betTypeID")
    entity = odd_obj.get("statEntityID")
    if bet_type == "ml" and entity in ("home", "away"):
        return "ml"
    if bet_type == "sp" and entity in ("home", "away"):
        return "sp"
    if bet_type == "ou" and entity == "all":
        return "ou"
    return None


def _side_of(odd_obj: dict) -> Optional[str]:
    side = odd_obj.get("sideID") or odd_obj.get("side")
    return str(side).lower() if side else None


def normalize_sportsgameodds_event(raw_event: dict, retrieved_at: str) -> Optional[NormalizedGameOdds]:
    """Returns None (never a partially-fabricated record) if the event
    is missing the minimum identity fields (event id, both teams)."""
    if not isinstance(raw_event, dict):
        return None

    parse_warnings: List[str] = []

    event_id = _first_present(raw_event, ["eventID", "id", "event_id"])
    if event_id is None:
        return None
    event_id = str(event_id)

    teams = raw_event.get("teams") if isinstance(raw_event.get("teams"), dict) else {}
    home_team = _team_abbreviation(teams.get("home")) or _team_abbreviation(raw_event.get("homeTeam"))
    away_team = _team_abbreviation(teams.get("away")) or _team_abbreviation(raw_event.get("awayTeam"))
    if not home_team or not away_team:
        return None

    status = raw_event.get("status") if isinstance(raw_event.get("status"), dict) else {}
    game_time_utc = _first_present({**status, **raw_event}, ["startsAt", "startTime", "commence_time", "date"])
    game_time_utc = str(game_time_utc) if game_time_utc is not None else None

    league = str(raw_event.get("leagueID") or raw_event.get("league") or "MLB").upper()

    odds_obj = raw_event.get("odds") if isinstance(raw_event.get("odds"), dict) else {}

    lines_by_book: Dict[str, BookLine] = {}

    def line_for(book: str) -> BookLine:
        if book not in lines_by_book:
            lines_by_book[book] = BookLine(book=book)
        return lines_by_book[book]

    for odd_id, odd_obj in odds_obj.items():
        if not isinstance(odd_obj, dict):
            continue

        market = _classify_market(odd_obj)
        if market is None:
            continue

        side = _side_of(odd_obj)
        book_entries = _iter_book_entries(odd_obj)
        if not book_entries:
            continue

        for entry in book_entries:
            book = entry["book"]
            line = line_for(book)
            american_odds = _safe_int(_first_present(entry, ["odds", "americanOdds", "price"]))
            updated_at = _first_present(entry, ["lastUpdatedAt", "updatedAt", "timestamp"])
            if updated_at is not None:
                line.last_updated = str(updated_at)

            if market == "ml":
                if side == "home":
                    line.home_moneyline = american_odds
                elif side == "away":
                    line.away_moneyline = american_odds
                else:
                    parse_warnings.append(f"Moneyline odd {odd_id!r} had no recognizable home/away side.")
            elif market == "sp":
                spread_value = _safe_float(_first_present(entry, ["spread", "line", "handicap"]))
                if side == "home":
                    line.home_run_line = spread_value
                    line.home_run_line_odds = american_odds
                elif side == "away":
                    line.away_run_line = spread_value
                    line.away_run_line_odds = american_odds
                else:
                    parse_warnings.append(f"Run line odd {odd_id!r} had no recognizable home/away side.")
            elif market == "ou":
                total_value = _safe_float(_first_present(entry, ["overUnder", "total", "line"]))
                if total_value is not None:
                    line.total = total_value
                if side == "over":
                    line.total_over_odds = american_odds
                elif side == "under":
                    line.total_under_odds = american_odds

    if not lines_by_book:
        parse_warnings.append(f"Event {event_id} had an odds object but no recognized moneyline/spread/total entries.")

    return NormalizedGameOdds(
        provider="sportsgameodds",
        event_id=event_id,
        league=league,
        home_team=home_team,
        away_team=away_team,
        game_time_utc=game_time_utc,
        retrieved_at=retrieved_at,
        books=list(lines_by_book.values()),
        parse_warnings=parse_warnings,
    )
