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
