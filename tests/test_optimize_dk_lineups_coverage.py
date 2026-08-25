import importlib

opt_script = importlib.import_module("scripts.optimize_dk_lineups")


def _pool_doc(n=3):
    return {"players": [{"name": f"Player {i}"} for i in range(n)]}


# ---------------------------------------------------------------------------
# Milestone 32.6 Part 2/3 -- _coverage_summary / _coverage_diagnostics.
#
# Reproduced live against a real DRAFTKINGS_UNOFFICIAL_LIVE slate: selecting
# any Projection Source (including the default, non-strict "native") on a
# slate whose research hadn't been generated yet produced a wall of generic
# "Only 0 eligible P player(s) available (need 2)." messages with zero
# indication of the real cause (0 of 746 pool players had a projection at
# all). These tests lock in the fix: --validate-only's JSON now carries a
# `coverage` object and leads `errors` with a clear Stage/Reason diagnostic
# whenever the pool shrank because of missing projections/strict-source
# exclusion, rather than a genuine roster/salary/stack conflict.
# ---------------------------------------------------------------------------


def test_coverage_summary_counts_every_bucket():
    coverage = opt_script._coverage_summary(
        _pool_doc(n=10), players=[1, 2], skipped=[3, 4, 5], excluded_missing_source=[6], projection_source="native", strict_source=False,
    )
    assert coverage == {
        "pool_size": 10,
        "optimizer_eligible": 6,  # 2 usable + 3 skipped + 1 excluded
        "usable_for_build": 2,
        "skipped_missing_projection": 3,
        "excluded_missing_source": 1,
        "projection_source": "native",
        "strict_source": False,
    }


def test_coverage_summary_full_coverage_has_zero_skipped_and_excluded():
    coverage = opt_script._coverage_summary(_pool_doc(n=2), players=[1, 2], skipped=[], excluded_missing_source=[], projection_source="native", strict_source=False)
    assert coverage["optimizer_eligible"] == 2
    assert coverage["usable_for_build"] == 2
    assert coverage["skipped_missing_projection"] == 0
    assert coverage["excluded_missing_source"] == 0


def test_diagnostics_empty_when_nothing_was_skipped_or_excluded():
    coverage = opt_script._coverage_summary(_pool_doc(n=2), players=[1, 2], skipped=[], excluded_missing_source=[], projection_source="native", strict_source=False)
    assert opt_script._coverage_diagnostics(coverage) == []


def test_diagnostics_flags_strict_source_exclusion_with_stage_and_reason():
    coverage = opt_script._coverage_summary(_pool_doc(n=5), players=[], skipped=[], excluded_missing_source=[1, 2, 3], projection_source="big_money_ml", strict_source=True)
    reasons = opt_script._coverage_diagnostics(coverage)
    assert len(reasons) >= 1
    assert reasons[0].startswith("Stage: Projection Source / Reason:")
    assert "3 otherwise-eligible player(s)" in reasons[0]
    assert "big_money_ml" in reasons[0]


def test_diagnostics_flags_missing_projection_with_stage_and_reason():
    coverage = opt_script._coverage_summary(_pool_doc(n=5), players=[], skipped=[1, 2, 3, 4, 5], excluded_missing_source=[], projection_source="native", strict_source=False)
    reasons = opt_script._coverage_diagnostics(coverage)
    assert any(r.startswith("Stage: Player Pool / Reason:") and "5 otherwise-eligible player(s)" in r for r in reasons)


def test_diagnostics_flags_zero_optimizer_eligible_at_all():
    """The live-repro shape: nobody in the pool is even optimizer_eligible
    yet (no confirmed starting lineups posted) -- distinct from "eligible
    but missing a projection"."""
    coverage = opt_script._coverage_summary(_pool_doc(n=746), players=[], skipped=[], excluded_missing_source=[], projection_source="native", strict_source=False)
    reasons = opt_script._coverage_diagnostics(coverage)
    assert any("0 of 746 pool player(s) are optimizer-eligible" in r for r in reasons)


def test_diagnostics_never_fires_when_pool_is_simply_empty_input():
    coverage = opt_script._coverage_summary({"players": []}, players=[], skipped=[], excluded_missing_source=[], projection_source="native", strict_source=False)
    # pool_size 0 -- "0 of 0" would be a nonsensical/misleading message, so
    # the zero-eligible diagnostic should still fire (true either way: 0
    # pool players means 0 optimizer_eligible players) -- assert it says 0/0
    # rather than being silently skipped.
    reasons = opt_script._coverage_diagnostics(coverage)
    assert any("0 of 0 pool player(s)" in r for r in reasons)


# ---------------------------------------------------------------------------
# Optimizer correctness hotfix -- _validate_only_errors.
#
# Reproduced live against a real DRAFTKINGS_UNOFFICIAL_LIVE Featured slate
# (652 pool players, 122 optimizer-eligible): selecting Big Money ML excluded
# 20 players for missing ML coverage, leaving 102 -- objectively plenty to
# build a legal 10-man lineup -- yet --validate-only's `errors` array was
# non-empty solely because excluded_missing_source > 0, so
# buildRunner.ts::buildLineups() refused to even attempt the solve.
# BlueCollar reproduced the identical failure (13 excluded, 109 remaining).
# These tests lock in the fix: a nonzero excluded/skipped count must NEVER
# block a build on its own -- only pre_solve_diagnostics() actually finding
# the shrunken pool infeasible may.
# ---------------------------------------------------------------------------


def test_validate_only_errors_empty_when_shrunken_pool_is_still_feasible():
    """The exact live-repro shape: coverage shrank (players excluded for
    missing strict-source coverage) but pre_solve_diagnostics() found
    nothing wrong with what remains -- must build, not refuse."""
    coverage = opt_script._coverage_summary(
        _pool_doc(n=122), players=list(range(102)), skipped=[], excluded_missing_source=list(range(20)),
        projection_source="big_money_ml", strict_source=True,
    )
    assert opt_script._validate_only_errors(coverage, solve_errors=[]) == []


def test_validate_only_errors_prepends_coverage_context_when_genuinely_infeasible():
    """When the shrunken pool really IS infeasible (pre_solve_diagnostics
    found a real problem), the coverage-shrinkage explanation is
    prepended so the user understands WHY, not just that a roster slot
    came up short."""
    coverage = opt_script._coverage_summary(
        _pool_doc(n=10), players=[], skipped=[], excluded_missing_source=[1, 2, 3],
        projection_source="bluecollar", strict_source=True,
    )
    solve_errors = ["Only 0 eligible C player(s) available (need 1)."]
    errors = opt_script._validate_only_errors(coverage, solve_errors)
    assert errors[0].startswith("Stage: Projection Source / Reason:")
    assert errors[-1] == "Only 0 eligible C player(s) available (need 1)."


def test_validate_only_errors_empty_when_nothing_shrank_and_nothing_infeasible():
    coverage = opt_script._coverage_summary(_pool_doc(n=2), players=[1, 2], skipped=[], excluded_missing_source=[], projection_source="native", strict_source=False)
    assert opt_script._validate_only_errors(coverage, solve_errors=[]) == []


def test_validate_only_errors_surfaces_a_leverage_config_error_even_with_full_coverage():
    """solve_errors can also come from leverage-mode config validation,
    entirely independent of coverage shrinkage -- must still surface."""
    coverage = opt_script._coverage_summary(_pool_doc(n=2), players=[1, 2], skipped=[], excluded_missing_source=[], projection_source="native", strict_source=False)
    solve_errors = ["--objective leverage requires --ownership (no player has a leverage_score)."]
    errors = opt_script._validate_only_errors(coverage, solve_errors)
    assert errors == solve_errors  # no coverage shrinkage to explain, so nothing prepended
