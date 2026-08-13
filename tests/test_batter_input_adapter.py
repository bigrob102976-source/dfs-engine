import json

import pytest

from models.batter import BatterInput
from research.adapters.batter_input import (
    ResearchPackageNotFoundError,
    build_batter_inputs,
    load_research_package,
    missing_lineup_games,
)

GAMES = [
    {
        "game_id": "111", "date": "2026-08-11", "game_datetime_utc": "2026-08-11T23:00:00Z",
        "status": "Pre-Game", "home_team_id": "20", "home_team_abbr": "BBB",
        "away_team_id": "10", "away_team_abbr": "AAA", "venue_id": "5", "venue_name": "Test Park",
        "home_probable_pitcher_id": "1001", "away_probable_pitcher_id": "1002", "game_number": 1,
    },
    {
        # No lineup posted for this one -- see PITCHERS-only, no BATTERS entries below.
        "game_id": "222", "date": "2026-08-11", "game_datetime_utc": "2026-08-11T20:00:00Z",
        "status": "Pre-Game", "home_team_id": "40", "home_team_abbr": "DDD",
        "away_team_id": "30", "away_team_abbr": "CCC", "venue_id": "6", "venue_name": "Other Park",
        "home_probable_pitcher_id": "1003", "away_probable_pitcher_id": "1004", "game_number": 1,
    },
]

TEAMS = [
    {"team_id": "10", "abbreviation": "AAA", "name": "Alpha Athletics"},
    {"team_id": "20", "abbreviation": "BBB", "name": "Beta Bears"},
    {"team_id": "30", "abbreviation": "CCC", "name": "Gamma Giants"},
    {"team_id": "40", "abbreviation": "DDD", "name": "Delta Ducks"},
]

BATTERS = [
    {"player_id": "2001", "name": "Home Batter One", "team_id": "20", "team_abbr": "BBB",
     "opponent_team_id": "10", "opponent_abbr": "AAA", "game_id": "111",
     "batting_order": 1, "position": "C", "bats": None, "status": "starting_lineup", "source": "mlb_stats_api"},
    {"player_id": "2002", "name": "Home Batter Two", "team_id": "20", "team_abbr": "BBB",
     "opponent_team_id": "10", "opponent_abbr": "AAA", "game_id": "111",
     "batting_order": 2, "position": "1B", "bats": None, "status": "starting_lineup", "source": "mlb_stats_api"},
    {"player_id": "3001", "name": "Away Batter One", "team_id": "10", "team_abbr": "AAA",
     "opponent_team_id": "20", "opponent_abbr": "BBB", "game_id": "111",
     "batting_order": 1, "position": "CF", "bats": None, "status": "starting_lineup", "source": "mlb_stats_api"},
]


def _write_package(tmp_path, slate_date="2026-08-11"):
    folder = tmp_path / slate_date
    folder.mkdir(parents=True)
    (folder / "games.json").write_text(json.dumps(GAMES), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps(TEAMS), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps(BATTERS), encoding="utf-8")
    return tmp_path, slate_date


def test_load_research_package_raises_when_missing(tmp_path):
    with pytest.raises(ResearchPackageNotFoundError):
        load_research_package(tmp_path, "2026-08-11")


def test_build_batter_inputs_creates_batterinput_instances(tmp_path):
    output_root, date = _write_package(tmp_path)
    package = load_research_package(output_root, date)
    batter_inputs = build_batter_inputs(package)

    assert len(batter_inputs) == 3
    assert all(isinstance(b, BatterInput) for b in batter_inputs)
    assert all(b.salary is None for b in batter_inputs)
    assert all(b.season.k_percent is None for b in batter_inputs)  # identity only, no stats yet


def test_build_batter_inputs_preserves_mlb_player_id_as_canonical_key(tmp_path):
    output_root, date = _write_package(tmp_path)
    batter_inputs = build_batter_inputs(load_research_package(output_root, date))
    ids = {b.player_id for b in batter_inputs}
    assert ids == {"2001", "2002", "3001"}
    for b in batter_inputs:
        assert b.player_id.isdigit()


def test_build_batter_inputs_preserves_batting_order(tmp_path):
    output_root, date = _write_package(tmp_path)
    batter_inputs = build_batter_inputs(load_research_package(output_root, date))
    by_id = {b.player_id: b for b in batter_inputs}
    assert by_id["2001"].batting_order == 1
    assert by_id["2002"].batting_order == 2
    assert by_id["3001"].batting_order == 1  # away team's own #1 hitter, independent of home team's order


def test_build_batter_inputs_maps_team_opponent_and_venue(tmp_path):
    output_root, date = _write_package(tmp_path)
    batter_inputs = build_batter_inputs(load_research_package(output_root, date))
    by_id = {b.player_id: b for b in batter_inputs}

    home = by_id["2001"]
    assert home.team == "BBB"
    assert home.opponent == "AAA"
    assert home.game_id == "111"
    assert home.venue_name == "Test Park"

    away = by_id["3001"]
    assert away.team == "AAA"
    assert away.opponent == "BBB"


def test_only_hitters_from_posted_lineups_are_present(tmp_path):
    """Game 222 has no batters.json entries at all (lineup not posted) --
    no hitter from that game should ever appear, and nothing should be
    guessed or manufactured for it."""
    output_root, date = _write_package(tmp_path)
    batter_inputs = build_batter_inputs(load_research_package(output_root, date))
    assert all(b.game_id != "222" for b in batter_inputs)


def test_missing_lineup_games_reports_the_gap(tmp_path):
    output_root, date = _write_package(tmp_path)
    package = load_research_package(output_root, date)
    missing = missing_lineup_games(package)
    assert len(missing) == 1
    assert missing[0]["game_id"] == "222"


def test_missing_lineup_games_empty_when_all_posted(tmp_path):
    output_root, date = _write_package(tmp_path)
    package = load_research_package(output_root, date)
    package["batters"].append({
        "player_id": "4001", "name": "X", "team_id": "40", "team_abbr": "DDD",
        "opponent_team_id": "30", "opponent_abbr": "CCC", "game_id": "222",
        "batting_order": 1, "position": "SS",
    })
    assert missing_lineup_games(package) == []
