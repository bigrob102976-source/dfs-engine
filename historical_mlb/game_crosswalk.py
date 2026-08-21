"""Game identity crosswalk (Milestone 32.0, Part 5).

MLB `gamePk` is the canonical game id here -- every source this package
touches already keys by it or can be joined to it: MLB Stats API
schedule/boxscore both use gamePk natively; Statcast rows carry their
own `game_pk` column (confirmed live: identical value space to MLB
Stats API's gamePk); the DraftKings unofficial provider's game
resolution (dfs/slate_validation.py::resolve_game_ids, reused as-is,
not duplicated here) already resolves DK's own competitionId ->
research gamePk for LIVE slates via date+team matching -- the same
fallback this module documents for historical dates when a gamePk
isn't already known.

Doubleheaders are the one case where "date + away + home" is NOT a
safe unique key -- both games of a doubleheader share date/away/home,
and MLB Stats API's schedule response distinguishes them via
`gameNumber` (1 or 2) and `doubleHeader` ("Y"/"N"/"S" for split-stadium
doubleheaders). This module's fallback key ALWAYS includes game_number,
specifically so two doubleheader games are never silently collapsed
into one row -- this was flagged as critical in Part 11's data-quality
checklist and is enforced structurally here, not just checked after the
fact.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class GameCrosswalkRow:
    canonical_game_id: str  # str(game_pk) when known
    game_pk: Optional[int] = None
    date: str = ""
    away_team: str = ""
    home_team: str = ""
    game_number: int = 1  # 1 or 2 -- doubleheader-safe
    double_header: Optional[str] = None  # "Y" | "N" | "S" (split-stadium), from MLB Stats API verbatim
    sportsdataio_game_id: Optional[str] = None
    dk_competition_id: Optional[str] = None


def fallback_key(date: str, away_team: str, home_team: str, game_number: int = 1) -> str:
    """The documented fallback identity when game_pk isn't available.
    ALWAYS includes game_number -- see this module's docstring for why
    omitting it would silently merge doubleheader games."""
    return f"{date}:{away_team}:{home_team}:g{game_number}"


def crosswalk_row_from_schedule_game(game: dict) -> GameCrosswalkRow:
    """Builds one row from historical_mlb.sources.mlb_stats.games_from_schedule()'s
    per-game dict shape."""
    game_pk = game.get("game_pk")
    return GameCrosswalkRow(
        canonical_game_id=str(game_pk) if game_pk is not None else fallback_key(
            game.get("game_date", ""), game.get("away_team", ""), game.get("home_team", ""), game.get("game_number", 1),
        ),
        game_pk=game_pk, date=game.get("game_date", ""),
        away_team=game.get("away_team", ""), home_team=game.get("home_team", ""),
        game_number=game.get("game_number", 1), double_header=game.get("double_header"),
    )


def build_game_index(rows: List[GameCrosswalkRow]) -> Dict[str, GameCrosswalkRow]:
    """Raises on a genuine duplicate canonical_game_id -- e.g. two
    schedule rows both missing game_pk and colliding on date+teams+
    game_number would indicate a real data problem (or, historically, a
    game replayed under identical circumstances), not something to
    silently overwrite."""
    index: Dict[str, GameCrosswalkRow] = {}
    for row in rows:
        if row.canonical_game_id in index:
            raise ValueError(f"Duplicate canonical_game_id in game crosswalk: {row.canonical_game_id!r}")
        index[row.canonical_game_id] = row
    return index
