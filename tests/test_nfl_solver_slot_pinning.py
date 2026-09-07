"""NFL M14 -- targeted tests for nfl/solver.py::solve_single_lineup()'s
new forced_slot_assignments parameter (the late-swap building block)."""

from nfl.optimizer_models import NflOptimizerSettings
from nfl.solver import solve_single_lineup
from tests._nfl_stack_fixtures import multi_team_pool


def test_forced_slot_assignment_pins_exact_slot():
    pool = multi_team_pool()
    result = solve_single_lineup(pool, NflOptimizerSettings(num_lineups=1), forced_slot_assignments={"QB": "TMA_qb"})
    assert result is not None
    qb_assignment = next(a for a in result if a[0] == "QB")
    assert qb_assignment[1].key == "TMA_qb"


def test_forced_slot_assignment_pins_flex_specifically():
    pool = multi_team_pool()
    result = solve_single_lineup(pool, NflOptimizerSettings(num_lineups=1), forced_slot_assignments={"FLEX": "TMA_rb1"})
    assert result is not None
    flex_assignment = next(a for a in result if a[0] == "FLEX")
    assert flex_assignment[1].key == "TMA_rb1"


def test_multiple_forced_slot_assignments_all_honored():
    pool = multi_team_pool()
    result = solve_single_lineup(pool, NflOptimizerSettings(num_lineups=1), forced_slot_assignments={
        "QB": "TMA_qb", "DST": "TMB_dst", "TE": "TMC_te",
    })
    assert result is not None
    by_slot = {label: p.key for label, p in result}
    assert by_slot["QB"] == "TMA_qb"
    assert by_slot["DST"] == "TMB_dst"
    assert by_slot["TE"] == "TMC_te"


def test_forced_slot_assignment_to_ineligible_slot_fails_cleanly():
    """A DST can never be forced into the QB slot -- not eligible."""
    pool = multi_team_pool()
    result = solve_single_lineup(pool, NflOptimizerSettings(num_lineups=1), forced_slot_assignments={"QB": "TMA_dst"})
    assert result is None


def test_forced_slot_assignment_to_unknown_slot_label_fails_cleanly():
    pool = multi_team_pool()
    result = solve_single_lineup(pool, NflOptimizerSettings(num_lineups=1), forced_slot_assignments={"NOT_A_SLOT": "TMA_qb"})
    assert result is None


def test_locked_player_survives_projection_mode_even_without_current_projection():
    """A player named in forced_slot_assignments must never be excluded
    by the scoring-mode eligibility filter, even with no projection --
    a locked player can never be dropped just because their data is stale."""
    pool = multi_team_pool(with_projections=True)
    # TMD_dst has no projection unless with_projections was set for every
    # position -- multi_team_pool(with_projections=True) DOES set it, so
    # instead explicitly null one player's projection to simulate stale data.
    for p in pool:
        if p.key == "TMA_qb":
            p.projection = None
            p.ceiling = None
    result = solve_single_lineup(
        pool, NflOptimizerSettings(mode="projection", num_lineups=1),
        forced_locks={"TMA_qb"}, forced_slot_assignments={"QB": "TMA_qb"},
    )
    assert result is not None
    qb_assignment = next(a for a in result if a[0] == "QB")
    assert qb_assignment[1].key == "TMA_qb"


def test_forced_slot_assignment_salary_still_counts_toward_cap():
    pool = multi_team_pool()
    # Force the most expensive QB into the QB slot with a very tight cap
    # -- must still respect the cap using that player's real salary.
    result = solve_single_lineup(
        pool, NflOptimizerSettings(num_lineups=1, salary_cap=15000), forced_slot_assignments={"QB": "TMA_qb"},
    )
    # TMA_qb costs 7500 -- either a legal cheap lineup is found respecting
    # the cap (including TMA_qb's real salary), or none exists; either way
    # the constraint must never be silently ignored.
    if result is not None:
        total_salary = sum(p.salary for _, p in result)
        assert total_salary <= 15000
        qb = next(p for label, p in result if label == "QB")
        assert qb.key == "TMA_qb"
