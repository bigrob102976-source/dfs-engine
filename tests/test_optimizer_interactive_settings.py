"""Milestone 14: the interactive dashboard build endpoint needs three
things the batch CLI never did -- a minimum salary spend, an overridable
CP-SAT time budget, and a pre-solve (no-solver) diagnostics check for a
live "what's wrong" panel. This covers all three without touching any
existing scoring/matching/optimization math.
"""

import pytest

from optimizer.constraints import OptimizerConfigError, pre_solve_diagnostics
from optimizer.lineup_generator import generate_lineups
from optimizer.models import OptimizerSettings
from optimizer.solver import solve_single_lineup
from optimizer.validator import validate_lineup

from ._optimizer_fixtures import feasible_pool


def test_min_salary_is_respected_by_the_solver():
    players = feasible_pool()
    settings = OptimizerSettings(min_salary=38000)
    assignment = solve_single_lineup(players, settings)
    assert assignment is not None
    total_salary = sum(p.salary for _, p in assignment)
    assert total_salary >= 38000
    assert total_salary <= settings.salary_cap


def test_min_salary_above_cap_is_infeasible():
    players = feasible_pool()
    settings = OptimizerSettings(min_salary=60000)  # above the $50,000 cap
    assert solve_single_lineup(players, settings) is None


def test_default_min_salary_is_none_and_unconstrained():
    players = feasible_pool()
    settings = OptimizerSettings()
    assert settings.min_salary is None
    assignment = solve_single_lineup(players, settings)
    assert assignment is not None


def test_validator_flags_lineup_below_min_salary():
    players = feasible_pool()
    output = generate_lineups(players, OptimizerSettings())  # build a real lineup with no floor
    lineup = output.result.lineups[0]

    # A floor above what this lineup actually spent -- must be flagged.
    too_high = validate_lineup(lineup, output.players_by_key, OptimizerSettings(min_salary=lineup.salary + 1))
    assert any("below the minimum spend" in v for v in too_high)

    # A floor at or below what it spent -- must NOT be flagged.
    satisfied = validate_lineup(lineup, output.players_by_key, OptimizerSettings(min_salary=lineup.salary))
    assert not any("below the minimum spend" in v for v in satisfied)


def test_time_limit_seconds_defaults_to_none_and_solve_still_works():
    players = feasible_pool()
    settings = OptimizerSettings()
    assert settings.time_limit_seconds is None
    assert solve_single_lineup(players, settings) is not None


def test_time_limit_seconds_override_still_produces_a_legal_lineup():
    """A short-but-not-absurd interactive time limit should still find a
    legal lineup on this small, easy fixture pool."""
    players = feasible_pool()
    settings = OptimizerSettings(time_limit_seconds=5.0)
    assignment = solve_single_lineup(players, settings)
    assert assignment is not None
    assert len(assignment) == 10


class TestPreSolveDiagnostics:
    def test_empty_when_nothing_obviously_wrong(self):
        players = feasible_pool()
        settings = OptimizerSettings()
        assert pre_solve_diagnostics(players, settings) == []

    def test_reports_locked_and_excluded_contradiction(self):
        players = feasible_pool()
        settings = OptimizerSettings(locks=["Phi C"], excludes=["Phi C"])
        errors = pre_solve_diagnostics(players, settings)
        assert len(errors) == 1
        assert "both locked and excluded" in errors[0]

    def test_reports_min_salary_above_cap(self):
        players = feasible_pool()
        settings = OptimizerSettings(min_salary=55000)
        errors = pre_solve_diagnostics(players, settings)
        assert any("exceeds the salary cap" in e for e in errors)

    def test_reports_insufficient_stack_team_hitters(self):
        players = feasible_pool()
        # BAL only has one hitter in the fixture pool.
        settings = OptimizerSettings(stack_size=5, stack_team="BAL")
        errors = pre_solve_diagnostics(players, settings)
        assert any("BAL only has" in e for e in errors)

    def test_reports_missing_position_coverage(self):
        # Only pitchers -- every hitter slot is unfillable.
        players = [p for p in feasible_pool() if p.player_type == "pitcher"]
        settings = OptimizerSettings()
        errors = pre_solve_diagnostics(players, settings)
        assert any("eligible C player" in e for e in errors)
        assert any("eligible OF player" in e for e in errors)

    def test_never_solves_even_when_pool_is_large(self):
        """Sanity: pre_solve_diagnostics must never invoke the CP-SAT
        solver -- it should return near-instantly regardless of pool size
        (this is a structural guarantee, verified by NOT mocking the
        solver and confirming the call returns without hanging)."""
        import time

        players = feasible_pool() * 5  # still tiny, but proves no per-lineup solve loop runs
        settings = OptimizerSettings(stack_size=3)
        started = time.monotonic()
        pre_solve_diagnostics(players, settings)
        assert time.monotonic() - started < 1.0

    def test_too_many_locked_pitchers_reported_exactly_like_the_milestone_example(self):
        """Milestone's own example: 'Unable to build: 3 pitchers are
        locked but only 2 pitcher slots exist.'"""
        players = feasible_pool()
        pitcher_names = [p.name for p in players if p.player_type == "pitcher"][:3]
        settings = OptimizerSettings(locks=pitcher_names)
        errors = pre_solve_diagnostics(players, settings)
        assert any("3 pitchers are locked but only 2 pitcher slot(s) exist" in e for e in errors)

    def test_locked_single_position_hitter_slot_overflow(self):
        """The same overflow check applies to any single-eligibility
        hitter slot, not just pitchers (2 catchers locked, only 1 C slot)."""
        players = feasible_pool()
        catcher_names = [p.name for p in players if p.player_type == "hitter" and p.dk_positions == ["C"]]
        assert len(catcher_names) >= 2
        settings = OptimizerSettings(locks=catcher_names[:2])
        errors = pre_solve_diagnostics(players, settings)
        assert any("2 C players are locked but only 1 C slot(s) exist" in e for e in errors)

    def test_two_locked_pitchers_is_fine(self):
        players = feasible_pool()
        pitcher_names = [p.name for p in players if p.player_type == "pitcher"][:2]
        settings = OptimizerSettings(locks=pitcher_names)
        errors = pre_solve_diagnostics(players, settings)
        assert not any("pitcher slot" in e for e in errors)

    def test_locked_multi_position_hitter_not_counted_against_either_single_slot(self):
        """A locked hitter eligible for BOTH 1B and OF isn't unambiguously
        assignable to either slot, so the overflow check deliberately
        leaves it to the solver rather than guessing."""
        players = feasible_pool()
        settings = OptimizerSettings(locks=["Min 1B Of"])
        errors = pre_solve_diagnostics(players, settings)
        assert not any("slot(s) exist" in e for e in errors)


def test_optimizer_config_error_still_raised_by_generate_lineups_for_contradictions():
    players = feasible_pool()
    settings = OptimizerSettings(locks=["Phi C"], excludes=["Phi C"])
    with pytest.raises(OptimizerConfigError):
        generate_lineups(players, settings)
