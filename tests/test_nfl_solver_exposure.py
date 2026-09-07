"""NFL M13 -- targeted tests for player exposure (min/max %), the
lock/exposure conflict rule, and leverage-mode end-to-end solving."""

import pytest

from nfl.constraints import (
    NflOptimizerConfigError,
    compute_exposure_count_caps,
    compute_min_exposure_targets,
    resolve_nfl_settings,
)
from nfl.optimizer_models import NflOptimizerSettings, NflStackConfig
from nfl.solver import generate_lineups
from tests._nfl_stack_fixtures import multi_team_pool


def test_max_exposure_count_cap_rounds_down():
    caps = compute_exposure_count_caps({"a": 0.25}, 1.0, 20, ["a", "b"])
    assert caps["a"] == 5  # floor(0.25*20)=5
    assert caps["b"] == 20  # default_fraction 1.0 -> unrestricted -> exactly num_lineups


def test_max_exposure_count_cap_truncates_not_rounds():
    # 0.26 * 20 = 5.2 -> int() truncates to 5, never rounds to 5 either way here,
    # but 0.29*10=2.9 -> int()=2 makes the truncation-not-rounding behavior unambiguous.
    caps = compute_exposure_count_caps({"a": 0.29}, 1.0, 10, ["a"])
    assert caps["a"] == 2


def test_min_exposure_target_rounds_up():
    targets = compute_min_exposure_targets({"a": 0.21}, 20)
    assert targets["a"] == 5  # ceil(0.21*20)=ceil(4.2)=5


def test_locked_player_with_max_exposure_below_one_is_a_conflict():
    pool = multi_team_pool()
    key = pool[0].key
    settings = NflOptimizerSettings(num_lineups=5, locks=[key], max_exposure={key: 0.5})
    with pytest.raises(NflOptimizerConfigError) as exc:
        resolve_nfl_settings(pool, settings)
    assert "locked" in str(exc.value).lower()


def test_locked_player_with_full_max_exposure_is_not_a_conflict():
    pool = multi_team_pool()
    key = pool[0].key
    settings = NflOptimizerSettings(num_lineups=5, locks=[key], max_exposure={key: 1.0})
    resolve_nfl_settings(pool, settings)  # must not raise


def test_excluded_player_with_min_exposure_is_a_conflict():
    pool = multi_team_pool()
    key = pool[0].key
    settings = NflOptimizerSettings(num_lineups=5, excludes=[key], min_exposure={key: 0.5})
    with pytest.raises(NflOptimizerConfigError):
        resolve_nfl_settings(pool, settings)


def test_out_of_range_exposure_fraction_rejected():
    pool = multi_team_pool()
    key = pool[0].key
    with pytest.raises(NflOptimizerConfigError):
        resolve_nfl_settings(pool, NflOptimizerSettings(num_lineups=5, max_exposure={key: 1.5}))
    with pytest.raises(NflOptimizerConfigError):
        resolve_nfl_settings(pool, NflOptimizerSettings(num_lineups=5, min_exposure={key: -0.1}))


def test_max_exposure_is_respected_across_generated_batch():
    pool = multi_team_pool()
    key = "TMA_wr1"  # a strong, cheap-relative-to-projection-free pool member the solver would otherwise favor often
    settings = NflOptimizerSettings(num_lineups=10, max_exposure={key: 0.3}, min_unique=1)
    result = generate_lineups(pool, settings)
    appearances = sum(1 for lu in result.lineups if key in lu.player_keys())
    # cap = int(0.3 * 10) = 3
    assert appearances <= 3


def test_min_exposure_is_respected_across_generated_batch():
    pool = multi_team_pool()
    key = "TMD_te"  # a weak, cheap player the solver would rarely pick unprompted
    settings = NflOptimizerSettings(num_lineups=10, min_exposure={key: 0.4}, min_unique=1)
    result = generate_lineups(pool, settings)
    appearances = sum(1 for lu in result.lineups if key in lu.player_keys())
    # target = ceil(0.4 * 10) = 4
    assert appearances >= 4


def test_locked_player_appears_in_every_lineup():
    pool = multi_team_pool()
    key = "TMD_dst"
    settings = NflOptimizerSettings(num_lineups=6, locks=[key], min_unique=1)
    result = generate_lineups(pool, settings)
    assert result.generated == 6
    assert all(key in lu.player_keys() for lu in result.lineups)


def test_leverage_mode_end_to_end_produces_valid_lineup():
    pool = multi_team_pool(with_projections=True, with_ownership=True)
    result = generate_lineups(pool, NflOptimizerSettings(mode="leverage", num_lineups=1))
    assert result.generated == 1
    lineup = result.lineups[0]
    assert lineup.mode == "leverage"
    assert lineup.total_leverage_score is not None
    assert lineup.total_projection is not None
    assert len(lineup.assignments) == 9


def test_ceiling_mode_end_to_end_maximizes_ceiling():
    pool = multi_team_pool(with_projections=True)
    result = generate_lineups(pool, NflOptimizerSettings(mode="ceiling", num_lineups=1))
    assert result.generated == 1
    lineup = result.lineups[0]
    assert lineup.mode == "ceiling"
    assert lineup.total_ceiling is not None and lineup.total_ceiling > 0


def test_leverage_mode_with_no_ownership_data_still_solves():
    """leverage_score missing everywhere must not block leverage mode --
    it just falls back to a plain projection/ceiling blend per player."""
    pool = multi_team_pool(with_projections=True, with_ownership=False)
    result = generate_lineups(pool, NflOptimizerSettings(mode="leverage", num_lineups=1))
    assert result.generated == 1
    assert result.lineups[0].total_leverage_score is None  # not every player had a leverage_score -- honestly None, not a partial sum


def test_stacking_and_exposure_together():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(
        num_lineups=8, stack=NflStackConfig(qb_stack_mode="single"), max_exposure_default=0.75, min_unique=1,
    )
    result = generate_lineups(pool, settings)
    assert result.generated >= 1
    for lu in result.lineups:
        assert lu.qb_stack_receiver_count >= 1
    key_sets = [frozenset(lu.player_keys()) for lu in result.lineups]
    assert len(set(key_sets)) == len(key_sets)
