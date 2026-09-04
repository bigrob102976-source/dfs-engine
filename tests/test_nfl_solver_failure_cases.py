"""NFL M13 Phase 21 -- failure cases must raise clear, specific errors
or report an honest, non-empty stopped_reason. No silent "0 lineups"
without a real explanation anywhere in this file."""

import pytest

from nfl.constraints import NflOptimizerConfigError
from nfl.optimizer_models import NflOptimizerSettings, NflStackConfig
from nfl.solver import generate_lineups
from tests._nfl_stack_fixtures import multi_team_pool


def test_impossible_double_stack_reports_clear_reason():
    """A pool with only 1 pass-catcher per team can never satisfy a
    double stack (needs 2) -- must fail loudly with a specific reason,
    never silently return 0 lineups with no explanation."""
    pool = [p for p in multi_team_pool() if p.position != "WR" or p.key.endswith("wr1")]  # strip down to 1 WR/team, keep TEs too... actually keep only 1 pass-catcher total per team
    pool = [p for p in pool if not (p.position == "TE")]  # remove TEs -- now each team has exactly 1 pass-catcher (wr1)
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(qb_stack_mode="double"))
    result = generate_lineups(pool, settings)
    assert result.generated == 0
    assert result.stopped_reason is not None
    assert "No legal lineup found" in result.stopped_reason
    assert "double" in result.stopped_reason.lower() or "stack" in result.stopped_reason.lower()


def test_locked_qb_with_no_eligible_teammates_reports_clear_reason():
    """Locking a QB whose team has zero eligible WR/TE (all excluded)
    while a stack is required must fail loudly, not silently drop the lock."""
    pool = multi_team_pool()
    tma_catchers = [p.key for p in pool if p.team == "TMA" and p.position in ("WR", "TE")]
    settings = NflOptimizerSettings(
        num_lineups=1, locks=["TMA_qb"], excludes=tma_catchers, stack=NflStackConfig(qb_stack_mode="single"),
    )
    result = generate_lineups(pool, settings)
    assert result.generated == 0
    assert result.stopped_reason is not None and len(result.stopped_reason) > 0


def test_bring_back_impossible_when_opponent_fully_excluded_reports_clear_reason():
    pool = multi_team_pool()
    tmb_all = [p.key for p in pool if p.team == "TMB"]  # TMA's entire opponent, TMB, excluded
    settings = NflOptimizerSettings(
        num_lineups=1, locks=["TMA_qb"], excludes=tmb_all,
        stack=NflStackConfig(qb_stack_mode="single", bring_back_mode="one"),
    )
    result = generate_lineups(pool, settings)
    assert result.generated == 0
    assert result.stopped_reason is not None


def test_max_exposure_conflicts_with_lock_raises_config_error():
    pool = multi_team_pool()
    key = pool[0].key
    settings = NflOptimizerSettings(num_lineups=5, locks=[key], max_exposure={key: 0.2})
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(pool, settings)


def test_max_players_per_team_too_restrictive_for_active_stack_raises_config_error():
    """Validated BEFORE any solve -- see nfl/constraints.py::validate_stack_config()."""
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(qb_stack_mode="double", max_players_per_team=2))
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(pool, settings)


def test_excluding_almost_everyone_reports_clear_reason_not_silent_zero():
    pool = multi_team_pool()
    # Exclude everything except one team's worth of players -- not
    # enough to fill 9 roster slots requiring 2 RB/3 WR/1 TE/1 DST/1 QB
    # from a single 8-player team (needs 2 RB but a team only has 2, so
    # actually just barely possible -- strip further to guarantee failure).
    keep = {"TMA_qb", "TMA_dst"}
    excludes = [p.key for p in pool if p.key not in keep]
    settings = NflOptimizerSettings(num_lineups=1, excludes=excludes)
    result = generate_lineups(pool, settings)
    assert result.generated == 0
    assert result.stopped_reason is not None and len(result.stopped_reason) > 0


def test_impossible_salary_cap_reports_clear_reason():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, salary_cap=5000)  # far below any legal 9-man roster cost
    result = generate_lineups(pool, settings)
    assert result.generated == 0
    assert result.stopped_reason is not None and "No legal lineup found" in result.stopped_reason


def test_unknown_objective_mode_raises_config_error():
    pool = multi_team_pool(with_projections=True)
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(pool, NflOptimizerSettings(mode="not_a_real_mode", num_lineups=1))


def test_bring_back_without_stack_rejected_before_solving():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(qb_stack_mode="off", bring_back_mode="one"))
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(pool, settings)
