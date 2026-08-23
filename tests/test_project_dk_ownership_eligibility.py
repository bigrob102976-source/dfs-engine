"""M32.7: proves scripts/project_dk_ownership.py::_build_input_players()
only ever projects ownership for optimizer_eligible players -- a
LINEUP_UNCONFIRMED/BENCH/RELIEF_PITCHER hitter or pitcher, even one with
a fully-populated projection/ceiling, must never receive an ownership
projection. This function had no dedicated test coverage before this
milestone (only an import-boundary check in
tests/test_architecture_separation.py)."""

import importlib

own_script = importlib.import_module("scripts.project_dk_ownership")


def _player(**overrides):
    base = {
        "dk_player_id": "d1", "mlb_player_id": "h1", "name": "Test Player", "team": "BOS",
        "opponent": "TOR", "game_id": "g1", "player_type": "hitter", "dk_positions": ["OF"],
        "salary": 4000, "projection": 10.0, "ceiling": 18.0, "risk_score": 30.0, "confidence": 80.0,
        "batting_order": 1, "eligibility_status": "STARTING_HITTER", "optimizer_eligible": True,
    }
    base.update(overrides)
    return base


def test_optimizer_eligible_player_is_included():
    pitchers, hitters, _fraction = own_script._build_input_players({"players": [_player()]})
    assert len(hitters) == 1
    assert len(pitchers) == 0


def test_lineup_unconfirmed_hitter_is_excluded_even_with_a_projection():
    doc = {"players": [_player(eligibility_status="LINEUP_UNCONFIRMED", optimizer_eligible=False)]}
    pitchers, hitters, _fraction = own_script._build_input_players(doc)
    assert hitters == []
    assert pitchers == []


def test_bench_hitter_is_excluded():
    doc = {"players": [_player(eligibility_status="BENCH", optimizer_eligible=False)]}
    _pitchers, hitters, _fraction = own_script._build_input_players(doc)
    assert hitters == []


def test_relief_pitcher_is_excluded():
    doc = {"players": [_player(
        player_type="pitcher", dk_positions=["P"], batting_order=None,
        eligibility_status="RELIEF_PITCHER", optimizer_eligible=False,
    )]}
    pitchers, _hitters, _fraction = own_script._build_input_players(doc)
    assert pitchers == []


def test_scratched_player_is_excluded():
    doc = {"players": [_player(eligibility_status="SCRATCHED", optimizer_eligible=False)]}
    _pitchers, hitters, _fraction = own_script._build_input_players(doc)
    assert hitters == []


def test_a_usable_projection_never_overrides_the_eligibility_gate():
    """The exact scenario this milestone calls out: projection
    AVAILABILITY must never imply optimizer eligibility, for ownership
    either -- an unconfirmed hitter with a perfectly good projection
    and ceiling is still excluded."""
    doc = {"players": [_player(
        eligibility_status="LINEUP_UNCONFIRMED", optimizer_eligible=False, projection=99.0, ceiling=150.0,
    )]}
    _pitchers, hitters, _fraction = own_script._build_input_players(doc)
    assert hitters == []


def test_eligible_player_missing_projection_is_still_excluded():
    doc = {"players": [_player(projection=None)]}
    _pitchers, hitters, _fraction = own_script._build_input_players(doc)
    assert hitters == []


def test_lineup_fraction_reflects_optimizer_eligible_count_over_total_rows():
    doc = {"players": [
        _player(dk_player_id="d1"),
        _player(dk_player_id="d2", eligibility_status="LINEUP_UNCONFIRMED", optimizer_eligible=False),
    ]}
    _pitchers, _hitters, fraction = own_script._build_input_players(doc)
    assert fraction == 0.5


def test_empty_pool_never_raises():
    pitchers, hitters, fraction = own_script._build_input_players({"players": []})
    assert pitchers == []
    assert hitters == []
    assert fraction == 0.0
