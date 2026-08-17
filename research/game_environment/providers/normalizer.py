"""Normalizes ONE raw SportsGameOdds v2 `/events` event object into a
provider-agnostic NormalizedGameOdds (providers/models.py).

This module makes a best-effort, defensively-coded parse of the v2
event/odds JSON shape, since this milestone's source of truth (the
instructions it was built from) documents the endpoint, filters, and
auth method precisely but does not hand over a full field-by-field
schema reference. Every extraction below tries a short list of
plausible, real SportsGameOdds v2 key names (verified against a live
response before this milestone shipped -- see the milestone's final
report for confirmation) rather than assuming a single guessed shape,
and anything that doesn't match gets recorded in `parse_warnings`
instead of silently dropped or crashing the whole event.

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

# Recognized SportsGameOdds oddID betType segments for the three markets
# this milestone collects. An oddID is a hyphen-joined string, e.g.
# "points-home-game-ml-home" (moneyline), "points-home-game-sp-home"
# (run line / spread), "points-all-game-ou-over" (total). Matched by
# substring rather than exact position so a minor key-shape difference
# (e.g. an extra segment) doesn't silently drop a whole market.
_MONEYLINE_MARKERS = ("-ml-",)
_SPREAD_MARKERS = ("-sp-",)
_TOTAL_MARKERS = ("-ou-",)


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
    """Each odd object carries a per-bookmaker breakdown under one of a
    few plausible key names; each entry is {book_name: {...fields...}}."""
    per_book = _first_present(odd_obj, ["byBookmaker", "bookOdds", "books", "bookmakers"])
    if not isinstance(per_book, dict):
        return []
    entries = []
    for book_name, book_data in per_book.items():
        if isinstance(book_data, dict):
            entries.append({"book": str(book_name), **book_data})
    return entries


def _odd_id_matches(odd_id: str, markers: tuple) -> bool:
    lowered = odd_id.lower()
    return any(marker in lowered for marker in markers)


def _side_of(odd_id: str, odd_obj: dict) -> Optional[str]:
    side = odd_obj.get("sideID") or odd_obj.get("side")
    if side:
        return str(side).lower()
    lowered = odd_id.lower()
    if lowered.endswith("-home") or "-home-" in lowered:
        return "home"
    if lowered.endswith("-away") or "-away-" in lowered:
        return "away"
    if lowered.endswith("-over"):
        return "over"
    if lowered.endswith("-under"):
        return "under"
    return None


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
        side = _side_of(str(odd_id), odd_obj)
        book_entries = _iter_book_entries(odd_obj)
        if not book_entries:
            continue

        is_ml = _odd_id_matches(str(odd_id), _MONEYLINE_MARKERS)
        is_sp = _odd_id_matches(str(odd_id), _SPREAD_MARKERS)
        is_ou = _odd_id_matches(str(odd_id), _TOTAL_MARKERS)
        if not (is_ml or is_sp or is_ou):
            continue

        for entry in book_entries:
            book = entry["book"]
            line = line_for(book)
            american_odds = _safe_int(_first_present(entry, ["odds", "americanOdds", "price"]))
            updated_at = _first_present(entry, ["lastUpdatedAt", "updatedAt", "timestamp"])
            if updated_at is not None:
                line.last_updated = str(updated_at)

            if is_ml:
                if side == "home":
                    line.home_moneyline = american_odds
                elif side == "away":
                    line.away_moneyline = american_odds
                else:
                    parse_warnings.append(f"Moneyline odd {odd_id!r} had no recognizable home/away side.")
            elif is_sp:
                spread_value = _safe_float(_first_present(entry, ["spread", "line", "handicap"]))
                if side == "home":
                    line.home_run_line = spread_value
                    line.home_run_line_odds = american_odds
                elif side == "away":
                    line.away_run_line = spread_value
                    line.away_run_line_odds = american_odds
                else:
                    parse_warnings.append(f"Run line odd {odd_id!r} had no recognizable home/away side.")
            elif is_ou:
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
