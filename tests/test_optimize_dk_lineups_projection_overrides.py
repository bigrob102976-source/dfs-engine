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
                "eligibility_status": "STARTING_HITTER", "optimizer_eligible": True,
            },
            {
                "dk_player_id": "d2", "mlb_player_id": "p1", "name": "Test Pitcher", "team": "TOR",
                "opponent": "BOS", "game_id": "g1", "player_type": "pitcher", "dk_positions": ["P"],
                "salary": 8000, "projection": 20.0, "ceiling": 32.0, "floor": 8.0, "risk_score": 25.0,
                "confidence": 90.0, "lineup_status": "active",
                "eligibility_status": "STARTING_PITCHER", "optimizer_eligible": True,
            },
        ],
    }


def test_no_overrides_is_byte_identical_to_pre_milestone_behavior():
    players, skipped, excluded = opt_script._build_optimizer_players(_pool_doc(), None)
    assert skipped == []
    assert excluded == []
    by_id = {p.key: p for p in players}
    assert by_id["d1"].projection == 10.0
    assert by_id["d2"].projection == 20.0


def test_overrides_swap_projection_for_matching_player_only():
    overrides = {"h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0}}
    players, _skipped, _excluded = opt_script._build_optimizer_players(_pool_doc(), overrides)
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
    players, _skipped, _excluded = opt_script._build_optimizer_players(_pool_doc(), overrides)
    by_id = {p.key: p for p in players}
    assert by_id["d1"].projection == 10.0  # override's projection was None -> fell back
    assert by_id["d1"].ceiling == 22.0  # override applied
    assert by_id["d1"].floor == 4.0  # override's floor was None -> fell back


# ---------------------------------------------------------------------------
# Milestone 32.4 -- strict_source (Big Money ML "no mixed-source fallback").
# ---------------------------------------------------------------------------


def test_strict_source_excludes_a_player_with_no_override_entry_at_all():
    """The core "ML-only means ML-only" guarantee: a player entirely
    absent from the overrides dict must be EXCLUDED, never silently
    fall back to the pool's own independent projection."""
    overrides = {"h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0}}  # p1 (pitcher) has no entry
    players, skipped, excluded = opt_script._build_optimizer_players(_pool_doc(), overrides, strict_source=True)
    by_id = {p.key: p for p in players}
    assert "d1" in by_id
    assert "d2" not in by_id
    assert skipped == []
    assert excluded == ["Test Pitcher"]


def test_strict_source_excludes_a_player_whose_override_projection_is_none():
    overrides = {
        "h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0},
        "p1": {"projection": None, "ceiling": 32.0, "floor": 8.0},
    }
    players, skipped, excluded = opt_script._build_optimizer_players(_pool_doc(), overrides, strict_source=True)
    by_id = {p.key: p for p in players}
    assert "d2" not in by_id
    assert excluded == ["Test Pitcher"]


def test_strict_source_never_falls_back_to_pool_independent_projection():
    """Same fixture as test_overrides_swap_projection_for_matching_player_only,
    but strict -- the pitcher (no override) must be excluded, NOT included
    with its own independent projection of 20.0."""
    overrides = {"h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0}}
    players, _skipped, _excluded = opt_script._build_optimizer_players(_pool_doc(), overrides, strict_source=True)
    assert all(p.projection != 20.0 for p in players)  # the pitcher's independent projection never leaks in
    assert len(players) == 1


def test_strict_source_still_uses_pool_ceiling_floor_fallback_when_override_omits_them():
    """Documented, deliberate exception: ceiling/floor fall back to the
    pool's own independent value even in strict mode, since the frozen
    Big Money ML models don't estimate ceiling/floor at all -- only the
    PROJECTION must be pure-ML."""
    overrides = {"h1": {"projection": 14.5, "ceiling": None, "floor": None}}
    players, _skipped, _excluded = opt_script._build_optimizer_players(_pool_doc(), overrides, strict_source=True)
    by_id = {p.key: p for p in players}
    assert by_id["d1"].projection == 14.5
    assert by_id["d1"].ceiling == 18.0  # pool's own independent ceiling
    assert by_id["d1"].floor == 4.0  # pool's own independent floor


def test_strict_source_with_full_coverage_excludes_nobody():
    overrides = {
        "h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0},
        "p1": {"projection": 25.0, "ceiling": 35.0, "floor": 10.0},
    }
    players, skipped, excluded = opt_script._build_optimizer_players(_pool_doc(), overrides, strict_source=True)
    assert len(players) == 2
    assert skipped == []
    assert excluded == []


def test_strict_source_false_is_the_default_and_unaffected():
    """strict_source defaults to False -- every pre-M32.4 call site
    (native/ai/fantasypros/external/adjusted) behaves identically without
    passing the new parameter at all."""
    overrides = {"h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0}}
    players, _skipped, excluded = opt_script._build_optimizer_players(_pool_doc(), overrides)
    by_id = {p.key: p for p in players}
    assert "d2" in by_id  # pitcher still included via independent fallback
    assert excluded == []


def test_load_projection_overrides_reads_json_file(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps({"h1": {"projection": 11.0}}), encoding="utf-8")
    loaded = opt_script._load_projection_overrides(str(path))
    assert loaded == {"h1": {"projection": 11.0}}


# ---------------------------------------------------------------------------
# M32.7 -- OPTIMIZER SAFETY: "Unconfirmed hitters remain optimizer_eligible
# = false. No optimizer source may bypass this. [Projection] availability
# must NOT imply optimizer eligibility." Covers BlueCollar and any other
# strict source (e.g. Big Money ML) identically, since the gate is
# entirely source-agnostic (optimizer_eligible is checked before any
# override is even consulted -- see _build_optimizer_players's own
# comment at the top of its loop).
# ---------------------------------------------------------------------------


def _pool_doc_with_unconfirmed_hitter():
    doc = _pool_doc()
    doc["players"].append({
        "dk_player_id": "d3", "mlb_player_id": "h2", "name": "Bench Hitter", "team": "BOS",
        "opponent": "TOR", "game_id": "g1", "player_type": "hitter", "dk_positions": ["OF"],
        "salary": 3000, "projection": None, "ceiling": None, "floor": None, "risk_score": None,
        "confidence": None, "lineup_status": "lineup_not_confirmed",
        "eligibility_status": "LINEUP_UNCONFIRMED", "optimizer_eligible": False,
    })
    return doc


def test_an_unconfirmed_hitter_with_a_usable_override_still_never_enters_the_optimizer_pool():
    """The exact scenario the milestone calls out by name: a BlueCollar
    (or any) projection source can have a perfectly usable, positive
    projection for a LINEUP_UNCONFIRMED hitter -- that availability must
    NEVER imply optimizer eligibility. Non-strict mode."""
    overrides = {"h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0}, "h2": {"projection": 9.5, "ceiling": None, "floor": None}}
    players, _skipped, _excluded = opt_script._build_optimizer_players(_pool_doc_with_unconfirmed_hitter(), overrides)
    assert all(p.key != "d3" for p in players)


def test_an_unconfirmed_hitter_with_a_usable_override_never_enters_the_pool_in_strict_mode_either():
    overrides = {
        "h1": {"projection": 14.5, "ceiling": 22.0, "floor": 6.0},
        "p1": {"projection": 25.0, "ceiling": 35.0, "floor": 10.0},
        "h2": {"projection": 9.5, "ceiling": None, "floor": None},
    }
    players, _skipped, excluded = opt_script._build_optimizer_players(_pool_doc_with_unconfirmed_hitter(), overrides, strict_source=True)
    assert all(p.key != "d3" for p in players)
    # Never even reaches the strict-source "excluded for missing
    # projection" bucket -- it's filtered out earlier, by eligibility,
    # for an entirely different reason.
    assert "Bench Hitter" not in excluded


def test_bench_and_scratched_players_are_equally_excluded_regardless_of_override_presence():
    for status in ("BENCH", "RELIEF_PITCHER", "SCRATCHED", "UNMATCHED", "AMBIGUOUS"):
        doc = _pool_doc()
        doc["players"].append({
            "dk_player_id": "dX", "mlb_player_id": "hX", "name": "Excluded Player", "team": "BOS",
            "opponent": "TOR", "game_id": "g1", "player_type": "hitter", "dk_positions": ["OF"],
            "salary": 3000, "projection": None, "ceiling": None, "floor": None, "risk_score": None,
            "confidence": None, "lineup_status": "x", "eligibility_status": status, "optimizer_eligible": False,
        })
        overrides = {"hX": {"projection": 99.0, "ceiling": 99.0, "floor": 99.0}}
        players, _skipped, _excluded = opt_script._build_optimizer_players(doc, overrides, strict_source=True)
        assert all(p.key != "dX" for p in players), f"status={status} leaked into the optimizer pool"
