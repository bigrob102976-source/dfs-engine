"""Milestone 32.5 -- Big Money ML forward RESULTS + LINEUP GRADING
tests. All network fetchers are monkeypatched (zero real HTTP calls);
every fixture is written to tmp_path so each test is fully isolated."""

import json

import pytest

import evaluation.ml_forward_grading as m
from evaluation.results_collector import RawResultsData


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# check_slate_final_status
# ---------------------------------------------------------------------------


def _pool_doc(players):
    return {"slate_date": "2026-08-22", "selected_slate_id": "dkunofficial-152547", "players": players}


def _pool_player(game_id, player_type="hitter"):
    return {"dk_player_id": f"d{game_id}", "mlb_player_id": f"p{game_id}", "player_type": player_type, "game_id": game_id}


def test_check_slate_final_status_gates_pregame_and_in_play_as_not_final(tmp_path, monkeypatch):
    dfs_root = tmp_path / "dfs_input"
    _write_json(dfs_root / "2026-08-22" / "dk_player_pool_1.json", _pool_doc([_pool_player("g1"), _pool_player("g2")]))

    def fake_schedule(date):
        return {"dates": [{"games": [
            {"gamePk": "g1", "status": {"detailedState": "In Progress"}},
            {"gamePk": "g2", "status": {"detailedState": "Pre-Game"}},
        ]}]}

    monkeypatch.setattr(m, "fetch_schedule", fake_schedule)
    status = m.check_slate_final_status("2026-08-22", "dkunofficial-152547", dfs_input_root=dfs_root)
    assert status["games_total"] == 2
    assert status["games_final"] == 0
    assert status["all_final"] is False


def test_check_slate_final_status_never_grades_suspended_as_final(tmp_path, monkeypatch):
    dfs_root = tmp_path / "dfs_input"
    _write_json(dfs_root / "2026-08-22" / "dk_player_pool_1.json", _pool_doc([_pool_player("g1")]))

    monkeypatch.setattr(m, "fetch_schedule", lambda date: {"dates": [{"games": [{"gamePk": "g1", "status": {"detailedState": "Suspended: Rain"}}]}]})
    status = m.check_slate_final_status("2026-08-22", "dkunofficial-152547", dfs_input_root=dfs_root)
    assert status["games_final"] == 0
    assert status["games"][0]["final"] is False


def test_check_slate_final_status_recognizes_final_and_final_variants(tmp_path, monkeypatch):
    dfs_root = tmp_path / "dfs_input"
    _write_json(dfs_root / "2026-08-22" / "dk_player_pool_1.json", _pool_doc([_pool_player("g1"), _pool_player("g2")]))

    monkeypatch.setattr(m, "fetch_schedule", lambda date: {"dates": [{"games": [
        {"gamePk": "g1", "status": {"detailedState": "Final"}},
        {"gamePk": "g2", "status": {"detailedState": "Final: Rain"}},
    ]}]})
    status = m.check_slate_final_status("2026-08-22", "dkunofficial-152547", dfs_input_root=dfs_root)
    assert status["games_final"] == 2
    assert status["all_final"] is True


def test_check_slate_final_status_partial_slate_reports_which_games_remain(tmp_path, monkeypatch):
    dfs_root = tmp_path / "dfs_input"
    _write_json(dfs_root / "2026-08-22" / "dk_player_pool_1.json", _pool_doc([_pool_player("g1"), _pool_player("g2"), _pool_player("g3")]))

    monkeypatch.setattr(m, "fetch_schedule", lambda date: {"dates": [{"games": [
        {"gamePk": "g1", "status": {"detailedState": "Final"}},
        {"gamePk": "g2", "status": {"detailedState": "In Progress"}},
        {"gamePk": "g3", "status": {"detailedState": "Final"}},
    ]}]})
    status = m.check_slate_final_status("2026-08-22", "dkunofficial-152547", dfs_input_root=dfs_root)
    assert status["games_final"] == 2
    assert status["all_final"] is False
    remaining = [g["game_id"] for g in status["games"] if not g["final"]]
    assert remaining == ["g2"]


def test_check_slate_final_status_no_pool_returns_empty_not_an_error(tmp_path, monkeypatch):
    dfs_root = tmp_path / "dfs_input"
    monkeypatch.setattr(m, "fetch_schedule", lambda date: {"dates": []})
    status = m.check_slate_final_status("2026-08-22", "dkunofficial-152547", dfs_input_root=dfs_root)
    assert status["games_total"] == 0
    assert status["all_final"] is False


# ---------------------------------------------------------------------------
# collect_and_score_final_games
# ---------------------------------------------------------------------------


def _boxscore(player_id, team_side="home", pitching=None, batting=None):
    stats = {}
    if pitching is not None:
        stats["pitching"] = pitching
    if batting is not None:
        stats["batting"] = batting
    return {"teams": {team_side: {"team": {"abbreviation": "NYY"}, "players": {f"ID{player_id}": {"stats": stats}}}}}


def test_collect_and_score_final_games_only_scores_players_from_final_games(tmp_path, monkeypatch):
    results_root = tmp_path / "results"

    raw = RawResultsData(
        date="2026-08-22",
        schedule={"dates": [{"games": [{"gamePk": "g1", "status": {"detailedState": "Final"}}]}]},
        boxscores={"g1": _boxscore("100", pitching={"gamesStarted": 1, "outs": 18, "strikeOuts": 7, "baseOnBalls": 2, "hits": 5, "earnedRuns": 2, "homeRuns": 1})},
    )
    monkeypatch.setattr(m, "collect_actual_results", lambda date, game_ids: raw)

    expected_pitchers = [{"player_id": "100", "name": "P100", "team": "NYY", "game_id": "g1"}]
    result = m.collect_and_score_final_games("2026-08-22", ["g1"], expected_pitchers, [], results_root=results_root)
    assert result["pitchers_graded"] == 1

    doc = json.loads((results_root / "2026-08-22" / "pitcher_results.json").read_text())
    assert doc["result_count"] == 1
    assert doc["results"][0]["dfs_points"] is not None


def test_collect_and_score_final_games_excludes_players_whose_game_is_not_yet_final(tmp_path, monkeypatch):
    """Only players whose game_id is in the FINAL set passed in are ever
    scored -- a player in a still-in-progress game is simply omitted
    from this collection pass, never marked with a fabricated result."""
    results_root = tmp_path / "results"
    raw = RawResultsData(date="2026-08-22", schedule={}, boxscores={})
    monkeypatch.setattr(m, "collect_actual_results", lambda date, game_ids: raw)

    expected_pitchers = [
        {"player_id": "100", "name": "Final Game Pitcher", "team": "NYY", "game_id": "g1"},
        {"player_id": "200", "name": "In Progress Pitcher", "team": "BOS", "game_id": "g2"},
    ]
    result = m.collect_and_score_final_games("2026-08-22", ["g1"], expected_pitchers, [], results_root=results_root)
    doc = json.loads((results_root / "2026-08-22" / "pitcher_results.json").read_text())
    assert doc["result_count"] == 1
    assert doc["results"][0]["player_id"] == "100"


def test_collect_and_score_final_games_hitter_scoring(tmp_path, monkeypatch):
    results_root = tmp_path / "results"
    raw = RawResultsData(
        date="2026-08-22",
        schedule={"dates": [{"games": [{"gamePk": "g1", "status": {"detailedState": "Final"}}]}]},
        boxscores={"g1": _boxscore("300", batting={"plateAppearances": 4, "atBats": 4, "hits": 2, "doubles": 1, "homeRuns": 1, "rbi": 3, "runs": 2, "baseOnBalls": 0})},
    )
    monkeypatch.setattr(m, "collect_actual_results", lambda date, game_ids: raw)

    expected_hitters = [{"player_id": "300", "name": "H300", "team": "NYY", "game_id": "g1"}]
    result = m.collect_and_score_final_games("2026-08-22", ["g1"], [], expected_hitters, results_root=results_root)
    assert result["hitters_graded"] == 1
    doc = json.loads((results_root / "2026-08-22" / "hitter_results.json").read_text())
    assert doc["results"][0]["dfs_points"] is not None


def test_collect_and_score_final_games_is_idempotent(tmp_path, monkeypatch):
    """Re-running with the same inputs must overwrite results/<date>/*.json
    with identical content -- never error, never duplicate."""
    results_root = tmp_path / "results"
    raw = RawResultsData(
        date="2026-08-22",
        schedule={"dates": [{"games": [{"gamePk": "g1", "status": {"detailedState": "Final"}}]}]},
        boxscores={"g1": _boxscore("100", pitching={"gamesStarted": 1, "outs": 18, "strikeOuts": 7, "baseOnBalls": 2, "hits": 5, "earnedRuns": 2, "homeRuns": 1})},
    )
    monkeypatch.setattr(m, "collect_actual_results", lambda date, game_ids: raw)
    expected_pitchers = [{"player_id": "100", "name": "P100", "team": "NYY", "game_id": "g1"}]

    m.collect_and_score_final_games("2026-08-22", ["g1"], expected_pitchers, [], results_root=results_root)
    m.collect_and_score_final_games("2026-08-22", ["g1"], expected_pitchers, [], results_root=results_root)  # no error
    doc = json.loads((results_root / "2026-08-22" / "pitcher_results.json").read_text())
    assert doc["result_count"] == 1


# ---------------------------------------------------------------------------
# build_player_grading_records
# ---------------------------------------------------------------------------


def test_build_player_grading_records_computes_error_and_absolute_error():
    sources = {"big_money_ml": {"1": 10.0, "2": 5.0}}
    actual = {"1": 14.0, "2": 3.0}
    identity = {"1": {"name": "A", "team": "NYY", "opponent": "BOS", "game_id": "g1"}}
    records = m.build_player_grading_records("2026-08-22", "hitter", sources, actual, identity)
    by_id = {r["player_id"]: r for r in records}
    assert by_id["1"]["error"] == 4.0
    assert by_id["1"]["absolute_error"] == 4.0
    assert by_id["2"]["error"] == -2.0
    assert by_id["2"]["absolute_error"] == 2.0
    assert by_id["1"]["team"] == "NYY"
    assert by_id["1"]["opponent"] == "BOS"


def test_build_player_grading_records_never_includes_a_player_without_both_projection_and_actual():
    sources = {"big_money_ml": {"1": 10.0, "unmatched": 5.0}}
    actual = {"1": 12.0}  # "unmatched" has a projection but no actual result yet
    records = m.build_player_grading_records("2026-08-22", "hitter", sources, actual, {})
    ids = {r["player_id"] for r in records}
    assert ids == {"1"}


def test_build_player_grading_records_falls_back_to_bare_player_id_when_identity_unknown():
    records = m.build_player_grading_records("2026-08-22", "hitter", {"native": {"9": 5.0}}, {"9": 6.0}, {})
    assert records[0]["name"] == "9"
    assert records[0]["team"] is None


# ---------------------------------------------------------------------------
# grade_one_lineup / grade_lineup_sets_for_slate
# ---------------------------------------------------------------------------


def _assignment(name, mlb_id, projection):
    return {"slot": "P", "dk_player_id": f"dk{mlb_id}", "mlb_player_id": mlb_id, "name": name, "team": "NYY", "opponent": "BOS", "salary": 5000, "projection": projection, "ceiling": None, "floor": None}


def test_grade_one_lineup_fully_graded_sums_actual_correctly():
    lineup = {"index": 1, "salary": 45000, "projection": 20.0, "assignments": [_assignment("A", "1", 10.0), _assignment("B", "2", 10.0)]}
    graded = m.grade_one_lineup(lineup, {"1": 12.0, "2": 8.0})
    assert graded["fully_graded"] is True
    assert graded["actual"] == 20.0
    assert graded["difference"] == 0.0
    assert graded["missing_players"] == []


def test_grade_one_lineup_partial_data_never_reports_a_fabricated_actual():
    lineup = {"index": 1, "salary": 45000, "projection": 20.0, "assignments": [_assignment("A", "1", 10.0), _assignment("B", "2", 10.0)]}
    graded = m.grade_one_lineup(lineup, {"1": 12.0})  # player "2" not graded yet
    assert graded["fully_graded"] is False
    assert graded["actual"] is None
    assert graded["missing_players"] == ["B"]


def test_grade_lineup_sets_for_slate_isolates_by_projection_source(tmp_path):
    lineups_root = tmp_path / "lineups"
    ml_doc = {
        "slate_date": "2026-08-22", "slate_id": "dkunofficial-152547", "projection_source": "big_money_ml",
        "lineups": [{"index": 1, "salary": 45000, "projection": 20.0, "assignments": [_assignment("A", "1", 10.0), _assignment("B", "2", 10.0)]}],
    }
    native_doc = {
        "slate_date": "2026-08-22", "slate_id": "dkunofficial-152547", "projection_source": "native",
        "lineups": [{"index": 1, "salary": 44000, "projection": 15.0, "assignments": [_assignment("C", "3", 15.0)]}],
    }
    _write_json(lineups_root / "2026-08-22" / "dk_lineups_1.json", ml_doc)
    _write_json(lineups_root / "2026-08-22" / "dk_lineups_2.json", native_doc)

    results_root = tmp_path / "results"
    _write_json(results_root / "2026-08-22" / "pitcher_results.json", {"results": []})
    _write_json(results_root / "2026-08-22" / "hitter_results.json", {"results": [
        {"player_id": "1", "dfs_points": 12.0}, {"player_id": "2", "dfs_points": 8.0}, {"player_id": "3", "dfs_points": 20.0},
    ]})

    ml_graded = m.grade_lineup_sets_for_slate("2026-08-22", "dkunofficial-152547", projection_source="big_money_ml", results_root=results_root, lineups_root=lineups_root)
    assert ml_graded["lineup_sets_found"] == 1
    assert ml_graded["highest_actual"] == 20.0

    native_graded = m.grade_lineup_sets_for_slate("2026-08-22", "dkunofficial-152547", projection_source="native", results_root=results_root, lineups_root=lineups_root)
    assert native_graded["lineup_sets_found"] == 1
    assert native_graded["highest_actual"] == 20.0  # player 3's own actual, unrelated to the ML lineup


def test_grade_lineup_sets_for_slate_ignores_a_different_slate_id(tmp_path):
    lineups_root = tmp_path / "lineups"
    _write_json(lineups_root / "2026-08-22" / "dk_lineups_1.json", {
        "slate_date": "2026-08-22", "slate_id": "dkunofficial-OTHER", "projection_source": "big_money_ml",
        "lineups": [{"index": 1, "salary": 45000, "projection": 20.0, "assignments": [_assignment("A", "1", 10.0)]}],
    })
    results_root = tmp_path / "results"
    graded = m.grade_lineup_sets_for_slate("2026-08-22", "dkunofficial-152547", results_root=results_root, lineups_root=lineups_root)
    assert graded["lineup_sets_found"] == 0


def test_compare_lineup_sources_for_slate_never_fabricates_a_missing_source(tmp_path):
    lineups_root = tmp_path / "lineups"
    _write_json(lineups_root / "2026-08-22" / "dk_lineups_1.json", {
        "slate_date": "2026-08-22", "slate_id": "dkunofficial-152547", "projection_source": "big_money_ml",
        "lineups": [{"index": 1, "salary": 45000, "projection": 20.0, "assignments": [_assignment("A", "1", 10.0)]}],
    })
    results_root = tmp_path / "results"
    _write_json(results_root / "2026-08-22" / "hitter_results.json", {"results": [{"player_id": "1", "dfs_points": 12.0}]})
    _write_json(results_root / "2026-08-22" / "pitcher_results.json", {"results": []})

    comparison = m.compare_lineup_sources_for_slate("2026-08-22", "dkunofficial-152547", ["big_money_ml", "native", "ai"], results_root=results_root, lineups_root=lineups_root)
    assert "big_money_ml" in comparison
    assert "native" not in comparison
    assert "ai" not in comparison
