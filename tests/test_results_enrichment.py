import pytest

from evaluation.results_collector import RawResultsData
from evaluation.results_enrichment import (
    STATUS_COMPLETED,
    STATUS_DID_NOT_START,
    STATUS_GAME_INCOMPLETE,
    STATUS_MISSING_RESULT,
    STATUS_POSTPONED,
    STATUS_SCRATCHED,
    parse_all_results,
    parse_pitcher_result,
)

RETRIEVED_AT = "2026-08-06T12:00:00+00:00"


def _schedule(game_id, detailed_state):
    return {"dates": [{"games": [{"gamePk": int(game_id), "status": {"detailedState": detailed_state}}]}]}


def _boxscore(home_pitchers, away_pitchers=None):
    def team_block(pitchers):
        players = {}
        for pid, stat in pitchers.items():
            players[f"ID{pid}"] = {"person": {"id": pid, "fullName": f"Player {pid}"}, "stats": {"pitching": stat}}
        return {"team": {"abbreviation": "AAA"}, "players": players}

    return {
        "teams": {
            "home": team_block(home_pitchers),
            "away": team_block(away_pitchers or {}),
        }
    }


def _starter_stat(**overrides):
    stat = {
        "gamesStarted": 1, "outs": 18, "battersFaced": 23, "strikeOuts": 8, "baseOnBalls": 2,
        "hits": 3, "earnedRuns": 3, "homeRuns": 1, "hitBatsmen": 0, "numberOfPitches": 93,
        "wins": 0, "losses": 0, "completeGames": 0, "shutouts": 0,
    }
    stat.update(overrides)
    return stat


# ----------------------------------------------------------------------------
# Player-ID matching + basic parsing
# ----------------------------------------------------------------------------


def test_parse_pitcher_result_completed_start_matches_by_id_not_name():
    raw = RawResultsData(
        date="2026-08-05",
        schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"686613": _starter_stat()})},
    )
    # Deliberately wrong "name" in the expected record -- matching must be by ID.
    expected = {"player_id": "686613", "name": "Totally Wrong Name", "team": "HOU", "game_id": "111"}
    result = parse_pitcher_result(raw, expected, RETRIEVED_AT)

    assert result.status == STATUS_COMPLETED
    assert result.player_id == "686613"
    assert result.outs == 18
    assert result.strikeouts == 8
    assert result.walks == 2
    assert result.hits_allowed == 3
    assert result.earned_runs == 3
    assert result.home_runs_allowed == 1
    assert result.pitch_count == 93
    assert result.innings_pitched == "6.0"


def test_parse_pitcher_result_decision_and_complete_game_bonuses():
    raw = RawResultsData(
        date="2026-08-05",
        schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"1": _starter_stat(wins=1, completeGames=1, shutouts=1, hits=0)})},
    )
    result = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "AAA", "game_id": "111"}, RETRIEVED_AT)

    assert result.win is True
    assert result.complete_game is True
    assert result.shutout is True
    assert result.no_hitter is True  # complete game + 0 hits allowed


# ----------------------------------------------------------------------------
# Status handling / failure cases
# ----------------------------------------------------------------------------


def test_status_postponed():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "Postponed"))
    result = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_POSTPONED
    assert result.outs is None


def test_status_game_incomplete():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "In Progress"))
    result = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_GAME_INCOMPLETE


def test_status_missing_result_when_game_not_in_schedule():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("999", "Final"))
    result = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_MISSING_RESULT


def test_status_missing_result_when_boxscore_fetch_failed():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "Final"), boxscores={})
    result = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_MISSING_RESULT


def test_status_missing_result_when_no_game_id_in_snapshot():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "Final"))
    result = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": None}, RETRIEVED_AT)
    assert result.status == STATUS_MISSING_RESULT


def test_status_scratched_when_pitcher_never_appears_in_boxscore():
    """Failure case: starter scratched after the snapshot was taken."""
    raw = RawResultsData(
        date="2026-08-05", schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"999": _starter_stat()})},  # a DIFFERENT pitcher started
    )
    expected = {"player_id": "1", "name": "Scratched Guy", "team": "A", "game_id": "111"}
    result = parse_pitcher_result(raw, expected, RETRIEVED_AT)
    assert result.status == STATUS_SCRATCHED


def test_status_did_not_start_for_opener_scenario():
    """Failure case: an opener started, our predicted "starter" only
    appeared in relief."""
    raw = RawResultsData(
        date="2026-08-05", schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"1": _starter_stat(gamesStarted=0, outs=9)})},
    )
    expected = {"player_id": "1", "name": "Piggyback Guy", "team": "A", "game_id": "111"}
    result = parse_pitcher_result(raw, expected, RETRIEVED_AT)
    assert result.status == STATUS_DID_NOT_START
    assert result.outs == 9  # real stats are still preserved, just not counted as a "start"


def test_pitcher_with_zero_ip_does_not_crash():
    """Failure case: starter recorded 0 outs (injured/ejected immediately)."""
    raw = RawResultsData(
        date="2026-08-05", schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"1": _starter_stat(outs=0, battersFaced=1, strikeOuts=0, hits=1, earnedRuns=1)})},
    )
    expected = {"player_id": "1", "name": "Short Outing", "team": "A", "game_id": "111"}
    result = parse_pitcher_result(raw, expected, RETRIEVED_AT)
    assert result.status == STATUS_COMPLETED
    assert result.outs == 0
    assert result.innings_pitched == "0.0"


def test_doubleheader_disambiguated_by_exact_game_id():
    """Two games same day, same team; only game_id (gamePk) distinguishes
    them -- no date-based ambiguity."""
    raw = RawResultsData(
        date="2026-08-05",
        schedule={"dates": [{"games": [
            {"gamePk": 111, "status": {"detailedState": "Final"}},
            {"gamePk": 112, "status": {"detailedState": "Final"}},
        ]}]},
        boxscores={
            "111": _boxscore({"1": _starter_stat(strikeOuts=5)}),
            "112": _boxscore({"1": _starter_stat(strikeOuts=9)}),
        },
    )
    game1 = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    game2 = parse_pitcher_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "112"}, RETRIEVED_AT)
    assert game1.strikeouts == 5
    assert game2.strikeouts == 9


def test_parse_all_results_processes_every_expected_pitcher():
    raw = RawResultsData(
        date="2026-08-05", schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"1": _starter_stat()})},
    )
    expected = [
        {"player_id": "1", "name": "Started", "team": "A", "game_id": "111"},
        {"player_id": "2", "name": "Scratched", "team": "A", "game_id": "111"},
    ]
    results = parse_all_results(raw, expected, RETRIEVED_AT)
    assert len(results) == 2
    assert results[0].status == STATUS_COMPLETED
    assert results[1].status == STATUS_SCRATCHED
