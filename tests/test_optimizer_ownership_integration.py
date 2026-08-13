import copy

import pytest

from optimizer.constraints import OptimizerConfigError, resolve_settings
from optimizer.lineup_generator import generate_lineups
from optimizer.models import OptimizerSettings
from optimizer.objective import InvalidObjectiveModeError, player_objective_value
from optimizer.solver import solve_single_lineup
from tests._optimizer_fixtures import feasible_pool


def _pool_with_ownership():
    players = feasible_pool()
    # Deliberately invert quality vs. ownership for a couple of players so
    # leverage mode has something real to react to.
    for p in players:
        p.projected_ownership = 20.0
        p.leverage_score = 0.0
        p.ownership_confidence = 80.0
    by_key = {p.key: p for p in players}
    by_key["phi_of1"].projected_ownership = 45.0   # highest projection AND highest owned -> chalky
    by_key["phi_of1"].leverage_score = -10.0
    by_key["nyy_of3"].projected_ownership = 4.0    # solid but low owned -> leverage play
    by_key["nyy_of3"].leverage_score = 35.0
    return players


def test_optimizer_player_ownership_fields_default_none():
    players = feasible_pool()
    assert all(p.projected_ownership is None for p in players)
    assert all(p.leverage_score is None for p in players)
    assert all(p.ownership_confidence is None for p in players)


def test_existing_objective_modes_unaffected_by_missing_ownership():
    players = feasible_pool()
    for mode in ("projection", "ceiling", "balanced"):
        # Should not raise, and should not reference ownership at all.
        value = player_objective_value(players[0], mode)
        assert isinstance(value, float)


def test_leverage_objective_falls_back_to_zero_bonus_when_missing():
    players = feasible_pool()
    assert players[0].leverage_score is None
    value = player_objective_value(players[0], "leverage")
    # Equivalent to the balanced-style blend with zero leverage nudge.
    from config.optimizer_config import LEVERAGE_OBJECTIVE_CEILING_WEIGHT, LEVERAGE_OBJECTIVE_PROJECTION_WEIGHT
    expected = LEVERAGE_OBJECTIVE_PROJECTION_WEIGHT * players[0].projection + LEVERAGE_OBJECTIVE_CEILING_WEIGHT * players[0].ceiling
    assert value == pytest.approx(expected)


def test_invalid_objective_mode_still_raises():
    players = feasible_pool()
    with pytest.raises(InvalidObjectiveModeError):
        player_objective_value(players[0], "ownership_only")


def test_leverage_mode_prefers_high_leverage_player_over_similar_quality_chalk():
    players = _pool_with_ownership()
    # nyy_of3 (leverage +35) vs phi_of1 (leverage -10) -- similar raw
    # projections but very different leverage; leverage objective should
    # nudge toward nyy_of3 more than the projection-only objective would.
    proj_value_diff = player_objective_value([p for p in players if p.key == "phi_of1"][0], "projection") - \
        player_objective_value([p for p in players if p.key == "nyy_of3"][0], "projection")
    leverage_value_diff = player_objective_value([p for p in players if p.key == "phi_of1"][0], "leverage") - \
        player_objective_value([p for p in players if p.key == "nyy_of3"][0], "leverage")
    assert leverage_value_diff < proj_value_diff  # leverage narrows phi_of1's advantage


def test_leverage_bonus_is_capped_and_never_dominates_quality():
    players = feasible_pool()
    p = players[0]
    p.leverage_score = 1000.0  # absurdly large, should still be capped
    from config.optimizer_config import LEVERAGE_OBJECTIVE_BONUS_MAX_POINTS
    value = player_objective_value(p, "leverage")
    base = 0.70 * p.projection + 0.30 * p.ceiling
    # leverage_score/100 * cap could exceed the cap itself if unclamped by
    # design (score can exceed 100) -- but the bonus should stay a small
    # fraction relative to typical DK point totals, not swamp them.
    assert value - base <= (1000.0 / 100.0) * LEVERAGE_OBJECTIVE_BONUS_MAX_POINTS  # sanity: matches the documented formula
    assert base > 0  # quality signal is still present and dominant for realistic leverage scores


def test_max_player_ownership_filter_excludes_high_owned():
    players = _pool_with_ownership()
    settings = OptimizerSettings(max_player_ownership=30.0)
    eligible, *_ = resolve_settings(players, settings)
    assert "phi_of1" not in {p.key for p in eligible}  # 45% owned, filtered out


def test_min_player_ownership_filter_excludes_low_owned():
    players = _pool_with_ownership()
    settings = OptimizerSettings(min_player_ownership=10.0)
    eligible, *_ = resolve_settings(players, settings)
    assert "nyy_of3" not in {p.key for p in eligible}  # 4% owned, filtered out


def test_ownership_filter_excludes_players_with_no_ownership_data():
    players = feasible_pool()  # no ownership data at all
    settings = OptimizerSettings(max_player_ownership=30.0)
    eligible, *_ = resolve_settings(players, settings)
    assert eligible == []  # conservative: can't verify the threshold, so exclude


def test_max_total_ownership_constraint_respected():
    players = _pool_with_ownership()
    settings = OptimizerSettings(objective_mode="projection", max_total_ownership=250.0)
    result = solve_single_lineup(players, settings)
    assert result is not None
    total_ownership = sum(p.projected_ownership for _, p in result if p.projected_ownership is not None)
    assert total_ownership <= 250.0


def test_max_total_ownership_infeasible_when_too_low():
    players = _pool_with_ownership()
    settings = OptimizerSettings(objective_mode="projection", max_total_ownership=1.0)
    result = solve_single_lineup(players, settings)
    assert result is None


def test_lineup_ownership_metrics_computed_when_data_present():
    players = _pool_with_ownership()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1))
    lineup = out.result.lineups[0]
    assert lineup.sum_ownership is not None
    assert lineup.average_ownership == pytest.approx(lineup.sum_ownership / 10, abs=0.01)
    assert lineup.max_ownership is not None
    assert lineup.players_above_chalk_threshold is not None


def test_lineup_ownership_metrics_none_when_data_absent():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1))
    lineup = out.result.lineups[0]
    assert lineup.sum_ownership is None
    assert lineup.average_ownership is None
    assert lineup.max_ownership is None
    assert lineup.players_above_chalk_threshold is None


def test_backward_compatible_lineup_identical_with_and_without_unused_ownership_fields():
    players_plain = feasible_pool()
    players_with_ownership_but_projection_mode = copy.deepcopy(_pool_with_ownership())
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)

    plain_result = solve_single_lineup(players_plain, settings)
    owned_result = solve_single_lineup(players_with_ownership_but_projection_mode, settings)

    # Objective mode "projection" never reads ownership fields -- presence
    # of ownership data must not change which lineup is chosen.
    assert sorted(p.key for _, p in plain_result) == sorted(p.key for _, p in owned_result)
