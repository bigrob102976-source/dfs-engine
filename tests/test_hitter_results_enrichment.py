from evaluation.hitter_results_enrichment import (
    STATUS_APPEARED,
    STATUS_GAME_INCOMPLETE,
    STATUS_MISSING_RESULT,
    STATUS_POSTPONED,
    STATUS_SCRATCHED,
    parse_all_hitter_results,
    parse_hitter_result,
)
from evaluation.results_collector import RawResultsData

RETRIEVED_AT = "2026-08-06T12:00:00+00:00"


def _schedule(game_id, detailed_state):
    return {"dates": [{"games": [{"gamePk": int(game_id), "status": {"detailedState": detailed_state}}]}]}


def _boxscore(home_hitters, away_hitters=None):
    def team_block(hitters):
        players = {}
        for pid, stat in hitters.items():
            players[f"ID{pid}"] = {"person": {"id": pid, "fullName": f"Player {pid}"}, "stats": {"batting": stat}}
        return {"team": {"abbreviation": "AAA"}, "players": players}

    return {
        "teams": {
            "home": team_block(home_hitters),
            "away": team_block(away_hitters or {}),
        }
    }


def _hitter_stat(**overrides):
    stat = {
        "plateAppearances": 5, "atBats": 4, "runs": 1, "hits": 2, "doubles": 1, "triples": 0,
        "homeRuns": 1, "rbi": 3, "baseOnBalls": 1, "strikeOuts": 1, "hitByPitch": 0, "stolenBases": 0,
    }
    stat.update(overrides)
    return stat


# ----------------------------------------------------------------------------
# Player-ID matching + basic parsing
# ----------------------------------------------------------------------------


def test_parse_hitter_result_appeared_matches_by_id_not_name():
    raw = RawResultsData(
        date="2026-08-05",
        schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"592450": _hitter_stat()})},
    )
    expected = {"player_id": "592450", "name": "Totally Wrong Name", "team": "PHI", "game_id": "111"}
    result = parse_hitter_result(raw, expected, RETRIEVED_AT)

    assert result.status == STATUS_APPEARED
    assert result.player_id == "592450"
    assert result.plate_appearances == 5
    assert result.at_bats == 4
    assert result.runs == 1
    assert result.hits == 2
    assert result.doubles == 1
    assert result.home_runs == 1
    assert result.rbi == 3
    assert result.walks == 1
    assert result.strikeouts == 1


# ----------------------------------------------------------------------------
# Status handling / failure cases
# ----------------------------------------------------------------------------


def test_status_postponed():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "Postponed"))
    result = parse_hitter_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_POSTPONED
    assert result.hits is None


def test_status_game_incomplete():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "In Progress"))
    result = parse_hitter_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_GAME_INCOMPLETE


def test_status_missing_result_when_game_not_in_schedule():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("999", "Final"))
    result = parse_hitter_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_MISSING_RESULT


def test_status_missing_result_when_boxscore_fetch_failed():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "Final"), boxscores={})
    result = parse_hitter_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    assert result.status == STATUS_MISSING_RESULT


def test_status_missing_result_when_no_game_id_in_snapshot():
    raw = RawResultsData(date="2026-08-05", schedule=_schedule("111", "Final"))
    result = parse_hitter_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": None}, RETRIEVED_AT)
    assert result.status == STATUS_MISSING_RESULT


def test_status_scratched_when_hitter_never_appears_in_boxscore():
    raw = RawResultsData(
        date="2026-08-05", schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"999": _hitter_stat()})},
    )
    expected = {"player_id": "1", "name": "Scratched Guy", "team": "A", "game_id": "111"}
    result = parse_hitter_result(raw, expected, RETRIEVED_AT)
    assert result.status == STATUS_SCRATCHED


def test_doubleheader_disambiguated_by_exact_game_id():
    raw = RawResultsData(
        date="2026-08-05",
        schedule={"dates": [{"games": [
            {"gamePk": 111, "status": {"detailedState": "Final"}},
            {"gamePk": 112, "status": {"detailedState": "Final"}},
        ]}]},
        boxscores={
            "111": _boxscore({"1": _hitter_stat(hits=1)}),
            "112": _boxscore({"1": _hitter_stat(hits=3)}),
        },
    )
    game1 = parse_hitter_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "111"}, RETRIEVED_AT)
    game2 = parse_hitter_result(raw, {"player_id": "1", "name": "X", "team": "A", "game_id": "112"}, RETRIEVED_AT)
    assert game1.hits == 1
    assert game2.hits == 3


def test_parse_all_hitter_results_processes_every_expected_hitter():
    raw = RawResultsData(
        date="2026-08-05", schedule=_schedule("111", "Final"),
        boxscores={"111": _boxscore({"1": _hitter_stat()})},
    )
    expected = [
        {"player_id": "1", "name": "Appeared", "team": "A", "game_id": "111"},
        {"player_id": "2", "name": "Scratched", "team": "A", "game_id": "111"},
    ]
    results = parse_all_hitter_results(raw, expected, RETRIEVED_AT)
    assert len(results) == 2
    assert results[0].status == STATUS_APPEARED
    assert results[1].status == STATUS_SCRATCHED
