"""NFL M13 -- targeted tests for nfl/objective.py's per-mode scoring
formula and mode-eligibility filtering."""

import pytest

from config.nfl_optimizer_config import NFL_LEVERAGE_BONUS_MAX_POINTS, NFL_LEVERAGE_CEILING_WEIGHT, NFL_LEVERAGE_PROJECTION_WEIGHT
from nfl.objective import InvalidNflObjectiveModeError, player_is_eligible_for_mode, player_objective_value, scaled_objective_value
from nfl.optimizer_models import NflOptimizerPlayer

DG_ID = 151307
DATE = "2026-09-13"


def _p(projection=None, ceiling=None, leverage_score=None):
    return NflOptimizerPlayer(
        key="1", name="Test", team="BUF", opponent="MIA", game_id="100", position="WR", roster_slots=["WR", "FLEX"],
        salary=6000, is_team_entity=False, draft_group_id=DG_ID, slate_date=DATE,
        projection=projection, ceiling=ceiling, leverage_score=leverage_score,
    )


def test_projection_mode_returns_projection_only():
    p = _p(projection=15.0, ceiling=25.0)
    assert player_objective_value(p, "projection") == 15.0


def test_ceiling_mode_returns_ceiling_only():
    p = _p(projection=15.0, ceiling=25.0)
    assert player_objective_value(p, "ceiling") == 25.0


def test_leverage_formula_matches_documented_weights():
    p = _p(projection=15.0, ceiling=25.0, leverage_score=40.0)
    expected_base = NFL_LEVERAGE_PROJECTION_WEIGHT * 15.0 + NFL_LEVERAGE_CEILING_WEIGHT * 25.0
    expected_nudge = (40.0 / 100.0) * NFL_LEVERAGE_BONUS_MAX_POINTS
    assert player_objective_value(p, "leverage") == pytest.approx(expected_base + expected_nudge)


def test_leverage_never_divides_by_ownership():
    """The formula must never divide by projected_ownership -- a
    division-by-zero trap NFL M13 Phase 9 explicitly forbids. Zero
    projected_ownership must not raise or produce infinity."""
    p = NflOptimizerPlayer(
        key="1", name="Test", team="BUF", opponent="MIA", game_id="100", position="WR", roster_slots=["WR", "FLEX"],
        salary=6000, is_team_entity=False, draft_group_id=DG_ID, slate_date=DATE,
        projection=15.0, ceiling=25.0, projected_ownership=0.0, leverage_score=10.0,
    )
    value = player_objective_value(p, "leverage")
    assert value == value  # not NaN
    assert value not in (float("inf"), float("-inf"))


def test_leverage_missing_score_falls_back_to_plain_blend_never_fabricated():
    """Missing leverage_score is handled explicitly (0 nudge), never
    excludes the player and never invents a score."""
    p = _p(projection=15.0, ceiling=25.0, leverage_score=None)
    expected_base = NFL_LEVERAGE_PROJECTION_WEIGHT * 15.0 + NFL_LEVERAGE_CEILING_WEIGHT * 25.0
    assert player_objective_value(p, "leverage") == pytest.approx(expected_base)


def test_leverage_nudge_is_small_relative_to_base():
    """Even a maximal leverage_score (100) can never make a weak player
    outscore a strong one -- the nudge is capped, never dominant."""
    weak = _p(projection=5.0, ceiling=8.0, leverage_score=100.0)
    strong = _p(projection=20.0, ceiling=30.0, leverage_score=-100.0)
    assert player_objective_value(strong, "leverage") > player_objective_value(weak, "leverage")


def test_unknown_mode_raises():
    with pytest.raises(InvalidNflObjectiveModeError):
        player_objective_value(_p(projection=1.0, ceiling=2.0), "not_a_mode")


def test_scaled_objective_value_is_an_integer():
    p = _p(projection=15.5, ceiling=25.5)
    value = scaled_objective_value(p, "projection")
    assert isinstance(value, int)
    assert value == 15500


def test_eligibility_roster_feasibility_always_true():
    assert player_is_eligible_for_mode(_p(), "roster_feasibility") is True


def test_eligibility_projection_requires_projection():
    assert player_is_eligible_for_mode(_p(projection=None), "projection") is False
    assert player_is_eligible_for_mode(_p(projection=10.0), "projection") is True


def test_eligibility_ceiling_requires_both_projection_and_ceiling():
    assert player_is_eligible_for_mode(_p(projection=10.0, ceiling=None), "ceiling") is False
    assert player_is_eligible_for_mode(_p(projection=None, ceiling=20.0), "ceiling") is False
    assert player_is_eligible_for_mode(_p(projection=10.0, ceiling=20.0), "ceiling") is True


def test_eligibility_leverage_requires_projection_and_ceiling_but_not_leverage_score():
    assert player_is_eligible_for_mode(_p(projection=10.0, ceiling=20.0, leverage_score=None), "leverage") is True
    assert player_is_eligible_for_mode(_p(projection=10.0, ceiling=None, leverage_score=50.0), "leverage") is False
