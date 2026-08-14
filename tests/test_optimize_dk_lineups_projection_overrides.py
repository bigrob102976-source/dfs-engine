import importlib
import json

opt_script = importlib.import_module("scripts.optimize_dk_lineups")


def _pool_doc():
    return {
        "players": [
            {
                "dk_player_id": "d1", "mlb_player_id": "h1", "name": "Test Hitter", "team": "BOS",
                "opponent": "TOR", "game_id": "g1", "player_type": "hitter", "dk_positions": ["OF"],
                "salary": 4000, "projection": 10.0, "ceiling": 18.0, "floor": 4.0, "risk_score": 30.0,
                "confidence": 80.0, "lineup_status": "active",
            },
            {
                "dk_player_id": "d2", "mlb_player_id": "p1", "name": "Test Pitcher", "team": "TOR",
                "opponent": "BOS", "game_id": "g1", "player_type": "pitcher", "dk_positions": ["P"],
                "salary": 8000, "projection": 20.0, "ceiling": 32.0, "floor": 8.0, "risk_score": 25.0,
                "confidence": 90.0, "lineup_status": "active",
            },
        ],
    }


def test_no_overrides_is_byte_identical_to_pre_milestone_behavior():
    players, skipped = opt_script._build_optimizer_players(_pool_doc(), None)
    assert skipped == []
    by_id = {p.key: p for p in players}
    assert by_id["d1"].projection == 10.0
    assert by_id["d2"].projection == 20.0


def test_overrides_swap_projection_for_matching_player_only():
    overrides = {"h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0}}
    players, _skipped = opt_script._build_optimizer_players(_pool_doc(), overrides)
    by_id = {p.key: p for p in players}
    assert by_id["d1"].projection == 14.5
    assert by_id["d1"].ceiling == 22.0
    assert by_id["d1"].floor == 6.0
    # Unmatched player (p1) keeps its ORIGINAL (independent) projection.
    assert by_id["d2"].projection == 20.0


def test_overrides_never_mutate_the_pool_doc():
    pool_doc = _pool_doc()
    original_projection = pool_doc["players"][0]["projection"]
    opt_script._build_optimizer_players(pool_doc, {"h1": {"projection": 999.0, "ceiling": 999.0, "floor": 999.0}})
    assert pool_doc["players"][0]["projection"] == original_projection


def test_overrides_missing_a_field_falls_back_to_pool_value():
    overrides = {"h1": {"projection": None, "ceiling": 22.0, "floor": None}}
    players, _skipped = opt_script._build_optimizer_players(_pool_doc(), overrides)
    by_id = {p.key: p for p in players}
    assert by_id["d1"].projection == 10.0  # override's projection was None -> fell back
    assert by_id["d1"].ceiling == 22.0  # override applied
    assert by_id["d1"].floor == 4.0  # override's floor was None -> fell back


def test_load_projection_overrides_reads_json_file(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps({"h1": {"projection": 11.0}}), encoding="utf-8")
    loaded = opt_script._load_projection_overrides(str(path))
    assert loaded == {"h1": {"projection": 11.0}}
