"""Validates a DraftKings slate against the MLB Research Package.

The DraftKings CSV defines the actual DFS slate -- our Research Package
may contain MLB games DraftKings excluded (e.g. a game moved to a
different night's slate) and, in principle, DraftKings could reference a
game our Research Package hasn't picked up. Neither direction should be
assumed away; both are detected and reported explicitly.

DraftKings' "Game Info" column uses the format "AWAY@HOME H:MMPM ET"
(e.g. "NYY@BOS 07:05PM ET"). When two research games share the same team
pair (a doubleheader), the embedded start time is used to disambiguate
by comparing it to each game's `game_datetime_utc` converted to
America/New_York (the timezone DraftKings always displays in). If that
still can't uniquely resolve it, the game is reported as an
ambiguous doubleheader rather than guessed.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Dict, List, Optional, Tuple

from dfs.models import DKSalaryRow
from dfs.team_abbreviations import normalize_dk_team_abbr

_GAME_INFO_RE = re.compile(r"^([A-Za-z]{2,3})@([A-Za-z]{2,3})\s+(\d{1,2}:\d{2}\s*[AaPp][Mm])")


@dataclass
class ParsedGameInfo:
    raw: str
    away_abbrev: Optional[str] = None
    home_abbrev: Optional[str] = None
    time_text: Optional[str] = None


@dataclass
class DKGameMatch:
    game_info: str
    dk_away: Optional[str]
    dk_home: Optional[str]
    research_game_id: Optional[str]
    status: str  # "matched" | "ambiguous_doubleheader" | "unmatched" | "unparseable"


@dataclass
class SlateValidation:
    dk_game_matches: Dict[str, DKGameMatch]
    research_games_not_on_dk_slate: List[dict] = field(default_factory=list)
    games_on_slate: set = field(default_factory=set)


def parse_game_info(raw: str) -> ParsedGameInfo:
    raw = (raw or "").strip()
    m = _GAME_INFO_RE.match(raw)
    if m:
        return ParsedGameInfo(raw=raw, away_abbrev=m.group(1).upper(), home_abbrev=m.group(2).upper(),
                               time_text=m.group(3).upper().replace(" ", ""))
    if "@" in raw:
        left, _, rest = raw.partition("@")
        tokens = rest.split()
        home = tokens[0].strip().upper() if tokens else None
        return ParsedGameInfo(raw=raw, away_abbrev=left.strip().upper() or None, home_abbrev=home or None)
    return ParsedGameInfo(raw=raw)


def _team_pair_index(games: List[dict]) -> Dict[frozenset, List[dict]]:
    index: Dict[frozenset, List[dict]] = {}
    for g in games:
        key = frozenset({g["home_team_abbr"], g["away_team_abbr"]})
        index.setdefault(key, []).append(g)
    return index


def _disambiguate_by_time(candidates: List[dict], time_text: Optional[str]) -> Optional[dict]:
    if not time_text:
        return None
    try:
        target = datetime.strptime(time_text, "%I:%M%p").time()
    except ValueError:
        return None

    from zoneinfo import ZoneInfo  # lazy import, same rationale as research/prediction_snapshot.py

    matches = []
    for g in candidates:
        dt_str = g.get("game_datetime_utc")
        if not dt_str:
            continue
        try:
            dt_utc = datetime.fromisoformat(dt_str)
        except ValueError:
            continue
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=dt_timezone.utc)
        dt_et = dt_utc.astimezone(ZoneInfo("America/New_York"))
        if dt_et.hour == target.hour and dt_et.minute == target.minute:
            matches.append(g)
    return matches[0] if len(matches) == 1 else None


def match_dk_games(dk_rows: List[DKSalaryRow], games: List[dict]) -> Dict[str, DKGameMatch]:
    """One DKGameMatch per DISTINCT Game Info string appearing in the CSV."""
    team_pair_index = _team_pair_index(games)
    results: Dict[str, DKGameMatch] = {}

    for game_info in sorted({r.game_info for r in dk_rows}):
        parsed = parse_game_info(game_info)
        if not parsed.away_abbrev or not parsed.home_abbrev:
            results[game_info] = DKGameMatch(game_info, parsed.away_abbrev, parsed.home_abbrev, None, "unparseable")
            continue

        research_away = normalize_dk_team_abbr(parsed.away_abbrev)
        research_home = normalize_dk_team_abbr(parsed.home_abbrev)
        candidates = team_pair_index.get(frozenset({research_away, research_home}), [])

        if not candidates:
            results[game_info] = DKGameMatch(game_info, parsed.away_abbrev, parsed.home_abbrev, None, "unmatched")
        elif len(candidates) == 1:
            results[game_info] = DKGameMatch(game_info, parsed.away_abbrev, parsed.home_abbrev, candidates[0]["game_id"], "matched")
        else:
            chosen = _disambiguate_by_time(candidates, parsed.time_text)
            if chosen:
                results[game_info] = DKGameMatch(game_info, parsed.away_abbrev, parsed.home_abbrev, chosen["game_id"], "matched")
            else:
                results[game_info] = DKGameMatch(game_info, parsed.away_abbrev, parsed.home_abbrev, None, "ambiguous_doubleheader")

    return results


def validate_slate(dk_rows: List[DKSalaryRow], package: dict) -> SlateValidation:
    games = package.get("games", [])
    dk_game_matches = match_dk_games(dk_rows, games)

    games_on_slate = {m.research_game_id for m in dk_game_matches.values() if m.research_game_id}
    research_games_not_on_dk_slate = [
        {"game_id": g["game_id"], "away_team_abbr": g["away_team_abbr"], "home_team_abbr": g["home_team_abbr"]}
        for g in games if g["game_id"] not in games_on_slate
    ]

    return SlateValidation(
        dk_game_matches=dk_game_matches,
        research_games_not_on_dk_slate=research_games_not_on_dk_slate,
        games_on_slate=games_on_slate,
    )
