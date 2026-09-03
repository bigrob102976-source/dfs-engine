import json

import pytest

from dfs.probable_starters import ProbableHitterInfo
from models.batter import BatterInput
from research.adapters.batter_input import (
    ResearchPackageNotFoundError,
    build_batter_inputs,
    build_batter_inputs_with_probables,
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


def _probable(mlb_id, name="Probable Player", team_abbr="DDD", opponent_abbr="CCC", game_id="222", order=3, on_roster=True):
    return ProbableHitterInfo(
        mlb_player_id=mlb_id, name=name, on_active_roster=on_roster, projected_batting_order=order,
        confidence="HIGH", reason="real evidence", recent_starts_considered=3, recent_starts_found=3,
        team_abbr=team_abbr, opponent_abbr=opponent_abbr, game_id=game_id,
    )


class TestBuildBatterInputsWithProbables:
    """PROBABLE FIX milestone: Native projections/ownership must be able
    to generate for a real, evidence-based probable starter, without
    waiting for the official lineup -- this is the merge point that feeds
    the Batter Agent's scoring pipeline both confirmed AND probable
    starters."""

    def test_confirmed_starters_always_included_unchanged(self, tmp_path):
        output_root, date = _write_package(tmp_path)
        package = load_research_package(output_root, date)
        result = build_batter_inputs_with_probables(package, {})
        assert {b.player_id for b in result} == {"2001", "2002", "3001"}

    def test_probable_starter_for_unposted_game_is_added(self, tmp_path):
        output_root, date = _write_package(tmp_path)
        package = load_research_package(output_root, date)
        probable = {("222", "5001"): _probable("5001")}
        result = build_batter_inputs_with_probables(package, probable)

        added = next(b for b in result if b.player_id == "5001")
        assert added.team == "DDD"
        assert added.opponent == "CCC"
        assert added.game_id == "222"
        assert added.batting_order == 3
        assert added.name == "Probable Player"  # real name, never a placeholder

    def test_off_active_roster_never_becomes_a_scoring_candidate(self, tmp_path):
        output_root, date = _write_package(tmp_path)
        package = load_research_package(output_root, date)
        probable = {("222", "5001"): _probable("5001", on_roster=False)}
        result = build_batter_inputs_with_probables(package, probable)
        assert all(b.player_id != "5001" for b in result)

    def test_official_lineup_always_wins_over_a_stale_probable_entry(self, tmp_path):
        """A probable_hitters entry for a player who's ALSO a real
        confirmed starter (e.g. a stale computation) must never produce a
        duplicate or override the real confirmed entry."""
        output_root, date = _write_package(tmp_path)
        package = load_research_package(output_root, date)
        probable = {("111", "2001"): _probable("2001", team_abbr="BBB", opponent_abbr="AAA", game_id="111", order=9)}
        result = build_batter_inputs_with_probables(package, probable)

        matches = [b for b in result if b.player_id == "2001"]
        assert len(matches) == 1  # never duplicated
        assert matches[0].batting_order == 1  # the REAL confirmed order, never the stale probable guess

    def test_missing_game_context_never_guessed(self, tmp_path):
        """A probable entry referencing a game_id not on this slate at
        all (shouldn't happen in practice, but defensively) is dropped,
        never fabricated into a BatterInput with empty team context."""
        output_root, date = _write_package(tmp_path)
        package = load_research_package(output_root, date)
        probable = {("nonexistent-game", "5001"): _probable("5001", game_id="nonexistent-game")}
        result = build_batter_inputs_with_probables(package, probable)
        assert all(b.player_id != "5001" for b in result)
