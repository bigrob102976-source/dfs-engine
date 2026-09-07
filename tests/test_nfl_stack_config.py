"""NFL M13 -- targeted tests for nfl/constraints.py::validate_stack_config()."""

import pytest

from nfl.constraints import NflOptimizerConfigError, validate_stack_config
from nfl.optimizer_models import NflStackConfig


def test_default_config_is_valid():
    validate_stack_config(NflStackConfig())


def test_single_stack_is_valid():
    validate_stack_config(NflStackConfig(qb_stack_mode="single"))


def test_double_stack_is_valid():
    validate_stack_config(NflStackConfig(qb_stack_mode="double"))


def test_unknown_qb_stack_mode_rejected():
    with pytest.raises(NflOptimizerConfigError):
        validate_stack_config(NflStackConfig(qb_stack_mode="triple"))


def test_unknown_bring_back_mode_rejected():
    with pytest.raises(NflOptimizerConfigError):
        validate_stack_config(NflStackConfig(bring_back_mode="two"))


def test_bring_back_without_qb_stack_rejected():
    with pytest.raises(NflOptimizerConfigError) as exc:
        validate_stack_config(NflStackConfig(qb_stack_mode="off", bring_back_mode="one"))
    assert "requires a QB stack" in str(exc.value)


def test_bring_back_with_qb_stack_is_valid():
    validate_stack_config(NflStackConfig(qb_stack_mode="single", bring_back_mode="one"))


def test_max_players_per_team_zero_rejected():
    with pytest.raises(NflOptimizerConfigError):
        validate_stack_config(NflStackConfig(max_players_per_team=0))


def test_max_players_per_game_zero_rejected():
    with pytest.raises(NflOptimizerConfigError):
        validate_stack_config(NflStackConfig(max_players_per_game=0))


def test_max_players_per_team_too_low_for_single_stack_rejected():
    """QB + 1 receiver needs 2 players minimum from one team."""
    with pytest.raises(NflOptimizerConfigError) as exc:
        validate_stack_config(NflStackConfig(qb_stack_mode="single", max_players_per_team=1))
    assert "too low" in str(exc.value)


def test_max_players_per_team_too_low_for_double_stack_rejected():
    """QB + 2 receivers needs 3 players minimum from one team."""
    with pytest.raises(NflOptimizerConfigError):
        validate_stack_config(NflStackConfig(qb_stack_mode="double", max_players_per_team=2))


def test_max_players_per_team_sufficient_for_double_stack_is_valid():
    validate_stack_config(NflStackConfig(qb_stack_mode="double", max_players_per_team=3))


def test_rb_dst_alone_is_valid():
    validate_stack_config(NflStackConfig(rb_dst_enabled=True))
