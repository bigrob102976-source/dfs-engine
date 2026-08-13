"""Enrichment stage for ACTUAL (postgame) pitcher results.

Pure data transformation on top of what evaluation.results_collector
already fetched -- no network calls here, so everything is testable with
plain fixture dicts. Mirrors research/enrichment.py's role on the
pregame side.

STATUS is the whole point of this module. A "completed_start" is never
assumed -- it has to be earned by (a) the game actually being Final,
(b) the pitcher actually appearing in that game's boxscore, and (c)
having actually started it:

    postponed         -- the game itself was postponed/cancelled
    game_incomplete    -- game exists but isn't Final yet (in progress,
                          suspended, delayed, etc.)
    missing_result     -- game should have a result but we couldn't get
                          one (schedule/boxscore fetch failure, or the
                          game_id wasn't found at all)
    scratched          -- game is Final, but this player never appears in
                          either team's boxscore at all
    did_not_start      -- game is Final, player appears, but did NOT
                          start (pitched in relief, e.g. an opener game)
    completed_start     -- game is Final, player started it

A doubleheader is handled implicitly, not as a special case: every
lookup is keyed by the exact game_id (gamePk) from the prediction
snapshot, and game 1 / game 2 of a doubleheader always have different
gamePks -- there is no date-based ambiguity to resolve.
"""

from dataclasses import dataclass
from typing import Optional

from evaluation.results_collector import RawResultsData
from research import innings

STATUS_COMPLETED = "completed_start"
STATUS_SCRATCHED = "scratched"
STATUS_DID_NOT_START = "did_not_start"
STATUS_POSTPONED = "postponed"
STATUS_GAME_INCOMPLETE = "game_incomplete"
STATUS_MISSING_RESULT = "missing_result"

_POSTPONED_KEYWORDS = ("Postponed", "Cancelled", "Canceled", "Suspended: Rain")


@dataclass
class ActualPitcherResult:
    player_id: str
    game_id: str
    game_date: str
    status: str

    name: Optional[str] = None
    team: Optional[str] = None

    outs: Optional[int] = None
    innings_pitched: Optional[str] = None  # baseball notation, e.g. "6.2"
    batters_faced: Optional[int] = None
    strikeouts: Optional[int] = None
    walks: Optional[int] = None
    hits_allowed: Optional[int] = None
    earned_runs: Optional[int] = None
    home_runs_allowed: Optional[int] = None
    hit_batsmen: Optional[int] = None
    pitch_count: Optional[int] = None

    win: Optional[bool] = None
    loss: Optional[bool] = None
    complete_game: Optional[bool] = None
    shutout: Optional[bool] = None
    no_hitter: Optional[bool] = None

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


def _find_pitcher_stat_block(boxscore: dict, player_id: str):
    """Search both teams' boxscore player lists for this player. Returns
    (pitching_stats_dict, team_abbr) or (None, None) if the player never
    appears in this game's boxscore at all."""
    for side in ("home", "away"):
        team_block = (boxscore.get("teams") or {}).get(side) or {}
        players = team_block.get("players") or {}
        player = players.get(f"ID{player_id}")
        if player:
            pitching = (player.get("stats") or {}).get("pitching")
            if pitching:
                team_abbr = ((team_block.get("team") or {}).get("abbreviation"))
                return pitching, team_abbr
    return None, None


def parse_pitcher_result(raw: RawResultsData, expected: dict, retrieved_at: str) -> ActualPitcherResult:
    """`expected` is one pitcher record from a prediction snapshot: at
    minimum player_id, name, team, game_id. Always returns a result --
    never raises, never silently skips a pitcher."""
    player_id = str(expected["player_id"])
    game_id = str(expected["game_id"]) if expected.get("game_id") else ""
    base = dict(
        player_id=player_id, game_id=game_id, game_date=raw.date,
        name=expected.get("name"), team=expected.get("team"),
        retrieved_at=retrieved_at,
    )

    if not game_id:
        return ActualPitcherResult(status=STATUS_MISSING_RESULT, **base)

    detailed_state = _find_game_status(raw.schedule, game_id)
    if detailed_state is None:
        return ActualPitcherResult(status=STATUS_MISSING_RESULT, **base)
    if any(keyword in detailed_state for keyword in _POSTPONED_KEYWORDS):
        return ActualPitcherResult(status=STATUS_POSTPONED, **base)
    if not detailed_state.startswith("Final"):
        return ActualPitcherResult(status=STATUS_GAME_INCOMPLETE, **base)

    boxscore = raw.boxscores.get(game_id)
    if not boxscore:
        return ActualPitcherResult(status=STATUS_MISSING_RESULT, **base)

    stat, team_abbr = _find_pitcher_stat_block(boxscore, player_id)
    if stat is None:
        return ActualPitcherResult(status=STATUS_SCRATCHED, **base)

    outs = _safe_int(stat.get("outs")) or 0
    hits_allowed = _safe_int(stat.get("hits")) or 0
    complete_game = bool(stat.get("completeGames"))
    shutout = bool(stat.get("shutouts"))
    no_hitter = complete_game and hits_allowed == 0

    result = ActualPitcherResult(
        status=STATUS_COMPLETED if stat.get("gamesStarted") else STATUS_DID_NOT_START,
        player_id=player_id, game_id=game_id, game_date=raw.date,
        name=expected.get("name"), team=team_abbr or expected.get("team"),
        outs=outs,
        innings_pitched=innings.outs_to_innings_notation(outs),
        batters_faced=_safe_int(stat.get("battersFaced")),
        strikeouts=_safe_int(stat.get("strikeOuts")),
        walks=_safe_int(stat.get("baseOnBalls")),
        hits_allowed=hits_allowed,
        earned_runs=_safe_int(stat.get("earnedRuns")),
        home_runs_allowed=_safe_int(stat.get("homeRuns")),
        hit_batsmen=_safe_int(stat.get("hitBatsmen")),
        pitch_count=_safe_int(stat.get("numberOfPitches")),
        win=bool(stat.get("wins")),
        loss=bool(stat.get("losses")),
        complete_game=complete_game,
        shutout=shutout,
        no_hitter=no_hitter,
        retrieved_at=retrieved_at,
    )
    return result


def parse_all_results(raw: RawResultsData, expected_pitchers, retrieved_at: str):
    return [parse_pitcher_result(raw, expected, retrieved_at) for expected in expected_pitchers]
