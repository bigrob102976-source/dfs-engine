import json

import pytest

from models.pitcher import PitcherInput
from research.adapters.pitcher_input import (
    ResearchPackageNotFoundError,
    build_pitcher_inputs,
    load_research_package,
)

GAMES = [
    {
        "game_id": "111", "date": "2026-08-11", "game_datetime_utc": "2026-08-11T23:00:00Z",
        "status": "Pre-Game", "home_team_id": "20", "home_team_abbr": "BBB",
        "away_team_id": "10", "away_team_abbr": "AAA", "venue_id": "5", "venue_name": "Test Park",
        "home_probable_pitcher_id": "1001", "away_probable_pitcher_id": "1002", "game_number": 1,
    },
    {
        "game_id": "222", "date": "2026-08-11", "game_datetime_utc": "2026-08-11T20:00:00Z",
        "status": "Pre-Game", "home_team_id": "40", "home_team_abbr": "DDD",
        "away_team_id": "30", "away_team_abbr": "CCC", "venue_id": "6", "venue_name": "Other Park",
        "home_probable_pitcher_id": "1003", "away_probable_pitcher_id": "1004", "game_number": 1,
    },
]

TEAMS = [
    {"team_id": "10", "abbreviation": "AAA", "name": "Alpha Athletics", "league": "AL", "division": "AL East"},
    {"team_id": "20", "abbreviation": "BBB", "name": "Beta Bears", "league": "AL", "division": "AL Central"},
    {"team_id": "30", "abbreviation": "CCC", "name": "Gamma Giants", "league": "NL", "division": "NL West"},
    {"team_id": "40", "abbreviation": "DDD", "name": "Delta Ducks", "league": "NL", "division": "NL East"},
]

PITCHERS = [
    {"player_id": "1001", "name": "Home Ace", "team_id": "20", "team_abbr": "BBB",
     "opponent_team_id": "10", "opponent_abbr": "AAA", "game_id": "111",
     "throws": "R", "status": "probable", "source": "mlb_stats_api"},
    {"player_id": "1002", "name": "Away Arm", "team_id": "10", "team_abbr": "AAA",
     "opponent_team_id": "20", "opponent_abbr": "BBB", "game_id": "111",
     "throws": "L", "status": "probable", "source": "mlb_stats_api"},
    {"player_id": "1003", "name": "Home Newcomer", "team_id": "40", "team_abbr": "DDD",
     "opponent_team_id": "30", "opponent_abbr": "CCC", "game_id": "222",
     "throws": "R", "status": "probable", "source": "mlb_stats_api"},
    {"player_id": "1004", "name": "Away Veteran", "team_id": "30", "team_abbr": "CCC",
     "opponent_team_id": "40", "opponent_abbr": "DDD", "game_id": "222",
     "throws": "L", "status": "probable", "source": "mlb_stats_api"},
]


def _write_package(tmp_path, slate_date="2026-08-11"):
    folder = tmp_path / slate_date
    folder.mkdir(parents=True)
    (folder / "games.json").write_text(json.dumps(GAMES), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps(TEAMS), encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps(PITCHERS), encoding="utf-8")
    return tmp_path, slate_date


def test_load_research_package_raises_when_missing(tmp_path):
    with pytest.raises(ResearchPackageNotFoundError):
        load_research_package(tmp_path, "2026-08-11")


def test_load_research_package_reads_files(tmp_path):
    output_root, date = _write_package(tmp_path)
    package = load_research_package(output_root, date)
    assert len(package["games"]) == 2
    assert len(package["teams"]) == 4
    assert len(package["pitchers"]) == 4


def test_build_pitcher_inputs_creates_pitcherinput_instances(tmp_path):
    output_root, date = _write_package(tmp_path)
    package = load_research_package(output_root, date)
    pitcher_inputs = build_pitcher_inputs(package)

    assert len(pitcher_inputs) == 4
    assert all(isinstance(p, PitcherInput) for p in pitcher_inputs)
    # Adapter resolves identity only -- salary is never invented, stats are unset.
    assert all(p.salary is None for p in pitcher_inputs)
    assert all(p.season.k_percent is None for p in pitcher_inputs)


def test_build_pitcher_inputs_preserves_mlb_player_id_as_canonical_key(tmp_path):
    output_root, date = _write_package(tmp_path)
    pitcher_inputs = build_pitcher_inputs(load_research_package(output_root, date))
    ids = {p.player_id for p in pitcher_inputs}
    assert ids == {"1001", "1002", "1003", "1004"}
    # Preserved as the MLB numeric ID (as a string), not derived from the name.
    for p in pitcher_inputs:
        assert p.player_id.isdigit()


def test_build_pitcher_inputs_maps_team_and_opponent_correctly(tmp_path):
    output_root, date = _write_package(tmp_path)
    pitcher_inputs = build_pitcher_inputs(load_research_package(output_root, date))
    by_id = {p.player_id: p for p in pitcher_inputs}

    home_ace = by_id["1001"]
    assert home_ace.team == "BBB"
    assert home_ace.opponent == "AAA"

    away_arm = by_id["1002"]
    assert away_arm.team == "AAA"
    assert away_arm.opponent == "BBB"


def test_opponent_team_resolution_does_not_cross_games(tmp_path):
    """A pitcher's opponent must come from their OWN game, never a
    different game happening on the same slate."""
    output_root, date = _write_package(tmp_path)
    pitcher_inputs = build_pitcher_inputs(load_research_package(output_root, date))
    by_id = {p.player_id: p for p in pitcher_inputs}

    assert by_id["1003"].opponent == "CCC"
    assert by_id["1003"].team == "DDD"
    assert by_id["1004"].opponent == "DDD"
    assert by_id["1004"].team == "CCC"
    # Cross-game team never leaks in as an opponent.
    assert by_id["1001"].opponent not in ("CCC", "DDD")


def test_build_pitcher_inputs_sets_probable_starter_status(tmp_path):
    output_root, date = _write_package(tmp_path)
    pitcher_inputs = build_pitcher_inputs(load_research_package(output_root, date))
    assert all(p.availability.confirmed_starter is True for p in pitcher_inputs)


def test_build_pitcher_inputs_resolves_game_id_and_venue(tmp_path):
    output_root, date = _write_package(tmp_path)
    pitcher_inputs = build_pitcher_inputs(load_research_package(output_root, date))
    by_id = {p.player_id: p for p in pitcher_inputs}

    assert by_id["1001"].game_id == "111"
    assert by_id["1001"].venue_name == "Test Park"
    assert by_id["1003"].game_id == "222"
    assert by_id["1003"].venue_name == "Other Park"


def test_build_pitcher_inputs_handles_missing_throws(tmp_path):
    output_root, date = _write_package(tmp_path)
    pitchers = json.loads((tmp_path / date / "pitchers.json").read_text(encoding="utf-8"))
    pitchers[0]["throws"] = None
    (tmp_path / date / "pitchers.json").write_text(json.dumps(pitchers), encoding="utf-8")

    pitcher_inputs = build_pitcher_inputs(load_research_package(output_root, date))
    by_id = {p.player_id: p for p in pitcher_inputs}
    assert by_id["1001"].throwing_hand is None
