"""Enrichment stage for ACTUAL (postgame) hitter results -- mirrors
evaluation/results_enrichment.py's role/discipline exactly (pure
transformation on data evaluation.results_collector already fetched, no
new network calls), reading the SAME already-cached boxscore payload
(RawResultsData.boxscores stores the full boxscore, not filtered to
pitching) so no second fetch is needed to support hitter evaluation.

STATUS, same honesty discipline as the pitcher side:

    postponed         -- the game itself was postponed/cancelled
    game_incomplete    -- game exists but isn't Final yet
    missing_result     -- game should have a result but we couldn't get one
    scratched          -- game is Final, but this player never appears in
                          either team's boxscore at all
    appeared           -- game is Final, player appears in the boxscore
                          (started or came off the bench -- DK scores both)
"""

from dataclasses import dataclass
from typing import Optional

from evaluation.results_collector import RawResultsData

STATUS_APPEARED = "appeared"
STATUS_SCRATCHED = "scratched"
STATUS_POSTPONED = "postponed"
STATUS_GAME_INCOMPLETE = "game_incomplete"
STATUS_MISSING_RESULT = "missing_result"

_POSTPONED_KEYWORDS = ("Postponed", "Cancelled", "Canceled", "Suspended: Rain")


@dataclass
class ActualHitterResult:
    player_id: str
    game_id: str
    game_date: str
    status: str

    name: Optional[str] = None
    team: Optional[str] = None

    plate_appearances: Optional[int] = None
    at_bats: Optional[int] = None
    runs: Optional[int] = None
    hits: Optional[int] = None
    doubles: Optional[int] = None
    triples: Optional[int] = None
    home_runs: Optional[int] = None
    rbi: Optional[int] = None
    walks: Optional[int] = None
    strikeouts: Optional[int] = None
    hit_by_pitch: Optional[int] = None
    stolen_bases: Optional[int] = None

    retrieved_at: str = ""
    source: str = "mlb_stats_api"


def _safe_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_game_status(schedule: dict, game_id: str) -> Optional[str]:
    for date_block in schedule.get("dates", []):
        for game in date_block.get("games", []):
            if str(game.get("gamePk")) == str(game_id):
                return (game.get("status") or {}).get("detailedState")
    return None


def _find_hitter_stat_block(boxscore: dict, player_id: str):
    """Search both teams' boxscore player lists for this player. Returns
    (batting_stats_dict, team_abbr) or (None, None) if the player never
    appears in this game's boxscore at all."""
    for side in ("home", "away"):
        team_block = (boxscore.get("teams") or {}).get(side) or {}
        players = team_block.get("players") or {}
        player = players.get(f"ID{player_id}")
        if player:
            batting = (player.get("stats") or {}).get("batting")
            if batting:
                team_abbr = (team_block.get("team") or {}).get("abbreviation")
                return batting, team_abbr
    return None, None


def parse_hitter_result(raw: RawResultsData, expected: dict, retrieved_at: str) -> ActualHitterResult:
    """`expected` is one hitter record from a native/prediction snapshot:
    at minimum player_id, name, team, game_id. Always returns a result --
    never raises, never silently skips a hitter."""
    player_id = str(expected["player_id"])
    game_id = str(expected["game_id"]) if expected.get("game_id") else ""
    base = dict(
        player_id=player_id, game_id=game_id, game_date=raw.date,
        name=expected.get("name"), team=expected.get("team"),
        retrieved_at=retrieved_at,
    )

    if not game_id:
        return ActualHitterResult(status=STATUS_MISSING_RESULT, **base)

    detailed_state = _find_game_status(raw.schedule, game_id)
    if detailed_state is None:
        return ActualHitterResult(status=STATUS_MISSING_RESULT, **base)
    if any(keyword in detailed_state for keyword in _POSTPONED_KEYWORDS):
        return ActualHitterResult(status=STATUS_POSTPONED, **base)
    if not detailed_state.startswith("Final"):
        return ActualHitterResult(status=STATUS_GAME_INCOMPLETE, **base)

    boxscore = raw.boxscores.get(game_id)
    if not boxscore:
        return ActualHitterResult(status=STATUS_MISSING_RESULT, **base)

    stat, team_abbr = _find_hitter_stat_block(boxscore, player_id)
    if stat is None:
        return ActualHitterResult(status=STATUS_SCRATCHED, **base)

    return ActualHitterResult(
        status=STATUS_APPEARED,
        player_id=player_id, game_id=game_id, game_date=raw.date,
        name=expected.get("name"), team=team_abbr or expected.get("team"),
        plate_appearances=_safe_int(stat.get("plateAppearances")),
        at_bats=_safe_int(stat.get("atBats")),
        runs=_safe_int(stat.get("runs")),
        hits=_safe_int(stat.get("hits")),
        doubles=_safe_int(stat.get("doubles")),
        triples=_safe_int(stat.get("triples")),
        home_runs=_safe_int(stat.get("homeRuns")),
        rbi=_safe_int(stat.get("rbi")),
        walks=_safe_int(stat.get("baseOnBalls")),
        strikeouts=_safe_int(stat.get("strikeOuts")),
        hit_by_pitch=_safe_int(stat.get("hitByPitch")),
        stolen_bases=_safe_int(stat.get("stolenBases")),
        retrieved_at=retrieved_at,
    )


def parse_all_hitter_results(raw: RawResultsData, expected_hitters, retrieved_at: str):
    return [parse_hitter_result(raw, expected, retrieved_at) for expected in expected_hitters]
