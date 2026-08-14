import json

from external_projections.csv_import.matcher import known_team_abbreviations, match_rows


def _write_research_package(root, date):
    folder = root / date
    folder.mkdir(parents=True)
    (folder / "games.json").write_text(json.dumps([
        {"game_id": "111", "home_team_abbr": "BOS", "away_team_abbr": "NYY"},
    ]), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps([
        {"team_id": "1", "abbreviation": "BOS", "name": "Red Sox", "league": "AL", "division": "East"},
        {"team_id": "2", "abbreviation": "NYY", "name": "Yankees", "league": "AL", "division": "East"},
    ]), encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps([
        {"player_id": "1001", "name": "Home Ace", "team_abbr": "BOS", "opponent_abbr": "NYY", "game_id": "111"},
    ]), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps([
        {"player_id": "2001", "name": "Aaron Judge", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "111", "position": "OF"},
        {"player_id": "2002", "name": "Duplicate Name", "team_abbr": "NYY", "opponent_abbr": "BOS", "game_id": "111", "position": "OF"},
        {"player_id": "2003", "name": "Duplicate Name", "team_abbr": "BOS", "opponent_abbr": "NYY", "game_id": "111", "position": "OF"},
    ]), encoding="utf-8")


def test_match_rows_finds_exact_name_team_matches(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    rows = [{"name": "Aaron Judge", "team": "NYY", "position": "OF", "player_id": None}]
    matches = match_rows(rows, str(tmp_path), "2026-08-11")
    assert matches[0].match_status == "matched"
    assert matches[0].mlb_player_id == "2001"


def test_match_rows_unmatched_for_unknown_player(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    rows = [{"name": "Nobody Real", "team": "NYY", "position": "OF", "player_id": None}]
    matches = match_rows(rows, str(tmp_path), "2026-08-11")
    assert matches[0].match_status == "unmatched"


def test_match_rows_ambiguous_when_name_only_and_multiple_teams(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    rows = [{"name": "Duplicate Name", "team": None, "position": "OF", "player_id": None}]
    matches = match_rows(rows, str(tmp_path), "2026-08-11")
    assert matches[0].match_status == "ambiguous"
    assert set(matches[0].candidate_mlb_ids) == {"2002", "2003"}


def test_match_rows_skips_rows_with_no_name(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    rows = [{"name": None, "team": "NYY", "position": "OF", "player_id": None}]
    matches = match_rows(rows, str(tmp_path), "2026-08-11")
    assert matches == []


def test_known_team_abbreviations(tmp_path):
    _write_research_package(tmp_path, "2026-08-11")
    assert known_team_abbreviations(str(tmp_path), "2026-08-11") == {"BOS", "NYY"}
