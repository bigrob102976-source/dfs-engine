"""PROBABLE FIX milestone: scripts/optimize_dk_lineups.py's "Use Probable
Starters" setting -- ON by default (probable starters included exactly
like confirmed ones), an explicit --exclude-probable-starters flag turns
it off for one build without affecting confirmed starters at all."""

import importlib

opt_script = importlib.import_module("scripts.optimize_dk_lineups")


def _confirmed_hitter(name="Confirmed Hitter"):
    return {
        "dk_player_id": "d1", "name": name, "team": "BOS", "opponent": "TOR", "game_id": "g1",
        "player_type": "hitter", "dk_positions": ["OF"], "salary": 4000,
        "mlb_player_id": "h1", "projection": 10.0, "ceiling": 15.0, "floor": 5.0,
        "optimizer_eligible": True, "eligibility_status": "STARTING_HITTER", "lineup_confirmation": "CONFIRMED",
    }


def _probable_hitter(name="Probable Hitter"):
    return {
        "dk_player_id": "d2", "name": name, "team": "BOS", "opponent": "TOR", "game_id": "g1",
        "player_type": "hitter", "dk_positions": ["OF"], "salary": 4000,
        "mlb_player_id": "h2", "projection": 9.0, "ceiling": 14.0, "floor": 4.0,
        "optimizer_eligible": True, "eligibility_status": "PROBABLE_HITTER", "lineup_confirmation": "PROBABLE",
    }


def _confirmed_pitcher(name="Confirmed Pitcher"):
    return {
        "dk_player_id": "d3", "name": name, "team": "BOS", "opponent": "TOR", "game_id": "g1",
        "player_type": "pitcher", "dk_positions": ["P"], "salary": 9000,
        "mlb_player_id": "p1", "projection": 20.0, "ceiling": 30.0, "floor": 10.0,
        "optimizer_eligible": True, "eligibility_status": "STARTING_PITCHER", "lineup_confirmation": "CONFIRMED",
    }


def _probable_pitcher(name="Probable Pitcher"):
    return {
        "dk_player_id": "d4", "name": name, "team": "BOS", "opponent": "TOR", "game_id": "g1",
        "player_type": "pitcher", "dk_positions": ["P"], "salary": 8500,
        "mlb_player_id": "p2", "projection": 18.0, "ceiling": 28.0, "floor": 9.0,
        "optimizer_eligible": True, "eligibility_status": "STARTING_PITCHER", "lineup_confirmation": "PROBABLE",
    }


class TestIsProbableStarter:
    def test_probable_hitter_is_probable(self):
        assert opt_script._is_probable_starter(_probable_hitter()) is True

    def test_confirmed_hitter_is_not_probable(self):
        assert opt_script._is_probable_starter(_confirmed_hitter()) is False

    def test_probable_pitcher_is_probable(self):
        assert opt_script._is_probable_starter(_probable_pitcher()) is True

    def test_confirmed_pitcher_is_not_probable(self):
        assert opt_script._is_probable_starter(_confirmed_pitcher()) is False

    def test_bench_and_relief_are_not_probable(self):
        assert opt_script._is_probable_starter({"eligibility_status": "BENCH"}) is False
        assert opt_script._is_probable_starter({"eligibility_status": "RELIEF_PITCHER"}) is False


class TestBuildOptimizerPlayersProbableToggle:
    def test_probable_starters_included_by_default(self):
        pool_doc = {"players": [_confirmed_hitter(), _probable_hitter(), _confirmed_pitcher(), _probable_pitcher()]}
        players, skipped, excluded = opt_script._build_optimizer_players(pool_doc)
        names = {p.name for p in players}
        assert names == {"Confirmed Hitter", "Probable Hitter", "Confirmed Pitcher", "Probable Pitcher"}
        assert skipped == []
        assert excluded == []

    def test_exclude_probable_starters_removes_only_probable_players(self):
        pool_doc = {"players": [_confirmed_hitter(), _probable_hitter(), _confirmed_pitcher(), _probable_pitcher()]}
        players, _, _ = opt_script._build_optimizer_players(pool_doc, exclude_probable_starters=True)
        names = {p.name for p in players}
        assert names == {"Confirmed Hitter", "Confirmed Pitcher"}

    def test_confirmed_starters_never_affected_by_the_toggle(self):
        pool_doc = {"players": [_confirmed_hitter(), _confirmed_pitcher()]}
        with_probable, _, _ = opt_script._build_optimizer_players(pool_doc, exclude_probable_starters=False)
        without_probable, _, _ = opt_script._build_optimizer_players(pool_doc, exclude_probable_starters=True)
        assert {p.name for p in with_probable} == {p.name for p in without_probable} == {"Confirmed Hitter", "Confirmed Pitcher"}
