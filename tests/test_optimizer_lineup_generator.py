from optimizer.lineup_generator import generate_lineups
from optimizer.models import OptimizerSettings
from tests._optimizer_fixtures import feasible_pool


def test_single_lineup_generated():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1))
    assert out.result.generated == 1
    assert out.result.stopped_reason is None


def test_multiple_lineups_are_pairwise_unique_min_unique_1():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=5, min_unique=1))
    lineups = out.result.lineups
    assert len(lineups) >= 2
    for i, a in enumerate(lineups):
        for b in lineups[i + 1:]:
            assert set(a.player_keys()) != set(b.player_keys())


def test_min_unique_2_enforced():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=4, min_unique=2))
    lineups = out.result.lineups
    for i, a in enumerate(lineups):
        for b in lineups[i + 1:]:
            shared = set(a.player_keys()) & set(b.player_keys())
            assert 10 - len(shared) >= 2


def test_min_unique_3_enforced():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=3, min_unique=3))
    lineups = out.result.lineups
    for i, a in enumerate(lineups):
        for b in lineups[i + 1:]:
            shared = set(a.player_keys()) & set(b.player_keys())
            assert 10 - len(shared) >= 3


def test_locks_appear_in_every_lineup():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=4, min_unique=1, locks=["Phi C"]))
    for lineup in out.result.lineups:
        assert "phi_c" in lineup.player_keys()


def test_multiple_locks_all_appear():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=3, min_unique=1, locks=["Phi C", "P Tor"]))
    for lineup in out.result.lineups:
        keys = lineup.player_keys()
        assert "phi_c" in keys
        assert "p_tor" in keys


def test_exclusions_never_appear():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=5, min_unique=1, excludes=["Phi Of1"]))
    for lineup in out.result.lineups:
        assert "phi_of1" not in lineup.player_keys()


def test_lock_and_exclusion_conflict_raises_before_solving():
    from optimizer.constraints import OptimizerConfigError
    players = feasible_pool()
    import pytest
    with pytest.raises(OptimizerConfigError):
        generate_lineups(players, OptimizerSettings(locks=["Phi C"], excludes=["Phi C"]))


def test_max_exposure_respected_across_lineups():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=6, min_unique=1, max_exposure={"Phi Of1": 0.5}))
    count = sum(1 for lu in out.result.lineups if "phi_of1" in lu.player_keys())
    assert count <= 3  # 0.5 * 6


def test_min_unique_still_enforced_when_a_previous_lineups_player_later_hits_exposure_cap():
    """Bug found live (M2, real 39-player slate): a tight stack thins the
    pool enough that once a player shared with an earlier lineup hits its
    own exposure cap and becomes dynamically excluded, the uniqueness
    constraint against that earlier lineup used to be skipped entirely
    (see optimizer/solver.py's fix comment) -- letting two generated
    lineups differ by fewer than min_unique players. Reproduced here with
    a tight PHI stack (only 7 eligible hitters) + a low cap on one of them."""
    players = feasible_pool()
    settings = OptimizerSettings(
        num_lineups=6, min_unique=2, stack_size=5, stack_team="PHI",
        max_exposure={"Phi Of1": 0.34},  # int(0.34 * 6) == 2
    )
    out = generate_lineups(players, settings)
    lineups = out.result.lineups
    assert len(lineups) >= 3
    for i, a in enumerate(lineups):
        for b in lineups[i + 1:]:
            shared = set(a.player_keys()) & set(b.player_keys())
            assert 10 - len(shared) >= 2, f"lineup {a.index} and {b.index} differ by only {10 - len(shared)} player(s)"


def test_insufficient_unique_lineups_reports_shortfall_without_duplicates():
    players = feasible_pool()
    # Locking 6 of 10 slots (5 PHI non-OF hitters, already at PHI's team
    # cap, + one pitcher) collapses the combinatorial space to a small,
    # exhaustible number of remaining OF/pitcher combinations -- request
    # far more than that.
    heavy_locks = ["Phi C", "Phi 1B", "Phi 2B", "Phi 3B", "Phi Ss", "P Tor"]
    out = generate_lineups(players, OptimizerSettings(num_lineups=100, min_unique=1, locks=heavy_locks))
    assert out.result.generated < 100
    assert out.result.stopped_reason is not None
    assert "100" in out.result.stopped_reason
    lineups = out.result.lineups
    seen = set()
    for lu in lineups:
        key = frozenset(lu.player_keys())
        assert key not in seen  # never duplicated just to pad the count
        seen.add(key)


def test_deterministic_repeat_generation():
    players = feasible_pool()
    settings = OptimizerSettings(num_lineups=5, min_unique=1)
    first = generate_lineups(players, settings)
    second = generate_lineups(players, settings)
    first_keys = [sorted(lu.player_keys()) for lu in first.result.lineups]
    second_keys = [sorted(lu.player_keys()) for lu in second.result.lineups]
    assert first_keys == second_keys
