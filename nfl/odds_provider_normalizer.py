"""NFL M7 -- normalizes raw odds-provider events into the shared,
provider-agnostic NormalizedGameOdds (research/game_environment/
providers/models.py), for NFL.

Why this is a SEPARATE module from research/game_environment/providers/
normalizer.py rather than a reused call, even though the market schema
these providers return is genuinely sport-agnostic (SportsGameOdds' own
statID/betTypeID/periodID/statEntityID taxonomy and The Odds API's own
h2h/spreads/totals markets are identical across leagues -- confirmed via
each provider's own public API docs, not guessed):

  research/game_environment/providers/normalizer.py's team-abbreviation
  resolution is hardwired to dfs/team_abbreviations.py::normalize_dk_
  team_abbr(), which is MLB's crosswalk. That table maps "ARI" -> "AZ"
  (Arizona's MLB research-package code) -- but "ARI" is also the REAL,
  correct DraftKings NFL abbreviation for the Arizona Cardinals (see
  config/nfl_team_abbreviations.py::DK_NFL_TEAM_ABBREVIATIONS). Reusing
  the MLB normalizer for NFL would silently rewrite every Arizona
  Cardinals event's team code to "AZ", which no NFL DK game would ever
  match -- a wrong-silent-corruption bug, not a hypothetical one. This
  project's NFL worktree is not permitted to modify MLB's normalizer
  (research/game_environment/ is exercised by the real MLB production
  pipeline) to fix this for both sports at once, so NFL gets its own
  team-resolution step instead, built on config/nfl_team_abbreviations.py.

  research/game_environment/providers/sportsgameodds.py::get_odds() and
  theoddsapi.py::get_odds() both call their sport's normalizer
  INTERNALLY and unconditionally -- there is no seam to inject a
  different team resolver through the public get_odds(league, date)
  method. This module's fetch_* functions therefore call each
  provider's already-real, already-tested raw-fetch method directly
  (SportsGameOddsProvider._fetch_all_pages / TheOddsAPIProvider._fetch)
  and apply NFL-specific normalization here -- reusing 100% of the real
  HTTP/auth/pagination/caching/error-handling logic, duplicating none of
  it, and never editing the MLB-adjacent provider files.

Market classification logic below (statID/periodID/betTypeID/
statEntityID checks, byBookmaker parsing) intentionally mirrors
research/game_environment/providers/normalizer.py's confirmed-real
SportsGameOdds parsing exactly -- same provider, same schema, same
verified field names (Milestone 24 live validation) -- only the team
resolution and league default differ.
"""

from typing import Any, Dict, List, Optional

from config.nfl_team_abbreviations import normalize_odds_provider_team_abbr
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


def _nfl_team_abbreviation(team_obj: Optional[dict]) -> Optional[str]:
    """Same field-extraction shape as research/game_environment/providers/
    normalizer.py::_team_abbreviation(), but resolved through NFL's own
    (currently pass-through, per config/nfl_team_abbreviations.py's
    documented "no real payload yet" state) crosswalk instead of MLB's."""
    if not isinstance(team_obj, dict):
        return None
    names = team_obj.get("names") if isinstance(team_obj.get("names"), dict) else {}
    candidate = _first_present(
        {**names, **team_obj},
        ["abbreviation", "short", "abbr", "code", "teamID"],
    )
    if candidate is None:
        return None
    return normalize_odds_provider_team_abbr(str(candidate))


def _iter_book_entries(odd_obj: dict) -> List[Dict[str, Any]]:
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


def normalize_sportsgameodds_event_nfl(raw_event: dict, retrieved_at: str) -> Optional[NormalizedGameOdds]:
    """NFL analog of research/game_environment/providers/normalizer.py::
    normalize_sportsgameodds_event() -- identical real, confirmed market
    parsing, NFL team resolution. Returns None (never a partially-
    fabricated record) if the event is missing the minimum identity
    fields (event id, both teams)."""
    if not isinstance(raw_event, dict):
        return None

    parse_warnings: List[str] = []

    event_id = _first_present(raw_event, ["eventID", "id", "event_id"])
    if event_id is None:
        return None
    event_id = str(event_id)

    teams = raw_event.get("teams") if isinstance(raw_event.get("teams"), dict) else {}
    home_team = _nfl_team_abbreviation(teams.get("home")) or _nfl_team_abbreviation(raw_event.get("homeTeam"))
    away_team = _nfl_team_abbreviation(teams.get("away")) or _nfl_team_abbreviation(raw_event.get("awayTeam"))
    if not home_team or not away_team:
        return None

    status = raw_event.get("status") if isinstance(raw_event.get("status"), dict) else {}
    game_time_utc = _first_present({**status, **raw_event}, ["startsAt", "startTime", "commence_time", "date"])
    game_time_utc = str(game_time_utc) if game_time_utc is not None else None

    league = str(raw_event.get("leagueID") or raw_event.get("league") or "NFL").upper()

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
                # Reusing BookLine's home_run_line/away_run_line fields
                # for NFL's point spread -- same "negative = home
                # favored" numeric convention (see nfl/game_context_
                # models.py::NflGameContext.spread's docstring), the
                # field names are simply inherited from BookLine's
                # baseball-first naming and never renamed downstream.
                spread_value = _safe_float(_first_present(entry, ["spread", "line", "handicap"]))
                if side == "home":
                    line.home_run_line = spread_value
                    line.home_run_line_odds = american_odds
                elif side == "away":
                    line.away_run_line = spread_value
                    line.away_run_line_odds = american_odds
                else:
                    parse_warnings.append(f"Spread odd {odd_id!r} had no recognizable home/away side.")
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
        event_status=status or None,
    )


# ---------------------------------------------------------------------------
# The Odds API (secondary/fallback provider) -- NFL
# ---------------------------------------------------------------------------
# Official v4 /sports/americanfootball_nfl/odds response shape (source of
# truth: https://the-odds-api.com/liveapi/guides/v4/, confirmed public
# docs): identical shape to the MLB endpoint this project already
# integrates -- home_team/away_team as full franchise names, bookmakers
# -> markets -> outcomes. NFL franchise full names are static, well-known
# public reference data (all 32 current teams), not a projection or
# invented statistic -- same category as dfs/team_abbreviations.py's own
# MLB_FULL_NAME_TO_ABBR table.

NFL_FULL_NAME_TO_DK_ABBR: Dict[str, str] = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR",
    "Las Vegas Raiders": "LV",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "Seattle Seahawks": "SEA",
    "San Francisco 49ers": "SF",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}


def _normalize_nfl_full_team_name(full_name: str) -> Optional[str]:
    """Maps a full NFL team name (as returned by The Odds API) onto
    DraftKings' own NFL abbreviation. Returns None (never a guess) for
    an unrecognized name."""
    if not full_name:
        return None
    return NFL_FULL_NAME_TO_DK_ABBR.get(full_name.strip())


def _theoddsapi_outcome_price(outcome: dict) -> Optional[int]:
    return _safe_int(outcome.get("price"))


def normalize_theoddsapi_event_nfl(raw_event: dict, retrieved_at: str) -> Optional[NormalizedGameOdds]:
    """NFL analog of research/game_environment/providers/normalizer.py::
    normalize_theoddsapi_event(). Returns None if the event is missing
    the minimum identity fields, or if either team name isn't a
    recognized NFL franchise."""
    if not isinstance(raw_event, dict):
        return None

    parse_warnings: List[str] = []

    event_id = raw_event.get("id")
    if event_id is None:
        return None
    event_id = str(event_id)

    home_team = _normalize_nfl_full_team_name(str(raw_event.get("home_team") or ""))
    away_team = _normalize_nfl_full_team_name(str(raw_event.get("away_team") or ""))
    if not home_team or not away_team:
        return None

    game_time_utc = raw_event.get("commence_time")
    game_time_utc = str(game_time_utc) if game_time_utc is not None else None

    league = str(raw_event.get("sport_key") or "americanfootball_nfl").upper()

    bookmakers = raw_event.get("bookmakers")
    if not isinstance(bookmakers, list):
        bookmakers = []

    lines_by_book: Dict[str, BookLine] = {}

    def line_for(book: str) -> BookLine:
        if book not in lines_by_book:
            lines_by_book[book] = BookLine(book=book)
        return lines_by_book[book]

    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            continue
        book_key = str(bookmaker.get("key") or bookmaker.get("title") or "")
        if not book_key:
            continue
        last_update = bookmaker.get("last_update")
        markets = bookmaker.get("markets")
        if not isinstance(markets, list):
            continue

        line = line_for(book_key)
        if last_update is not None:
            line.last_updated = str(last_update)

        for market in markets:
            if not isinstance(market, dict):
                continue
            market_key = market.get("key")
            outcomes = market.get("outcomes")
            if not isinstance(outcomes, list):
                continue

            if market_key == "h2h":
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    team = _normalize_nfl_full_team_name(str(outcome.get("name") or ""))
                    price = _theoddsapi_outcome_price(outcome)
                    if team == home_team:
                        line.home_moneyline = price
                    elif team == away_team:
                        line.away_moneyline = price
                    else:
                        parse_warnings.append(f"h2h outcome {outcome.get('name')!r} did not match either team.")

            elif market_key == "spreads":
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    team = _normalize_nfl_full_team_name(str(outcome.get("name") or ""))
                    point = _safe_float(outcome.get("point"))
                    price = _theoddsapi_outcome_price(outcome)
                    if team == home_team:
                        line.home_run_line = point
                        line.home_run_line_odds = price
                    elif team == away_team:
                        line.away_run_line = point
                        line.away_run_line_odds = price

            elif market_key == "totals":
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    name = str(outcome.get("name") or "").strip().lower()
                    point = _safe_float(outcome.get("point"))
                    price = _theoddsapi_outcome_price(outcome)
                    if point is not None:
                        line.total = point
                    if name == "over":
                        line.total_over_odds = price
                    elif name == "under":
                        line.total_under_odds = price

    if not lines_by_book:
        parse_warnings.append(f"Event {event_id} had bookmakers but no recognized h2h/spreads/totals entries.")

    return NormalizedGameOdds(
        provider="theoddsapi",
        event_id=event_id,
        league=league,
        home_team=home_team,
        away_team=away_team,
        game_time_utc=game_time_utc,
        retrieved_at=retrieved_at,
        books=list(lines_by_book.values()),
        parse_warnings=parse_warnings,
        event_status=None,
    )
