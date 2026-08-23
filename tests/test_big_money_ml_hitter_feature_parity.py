"""Milestone 32.3B -- training/live HITTER feature parity report tests.
Mirrors tests/test_big_money_ml_feature_parity.py exactly."""

from big_money_ml.hitter_feature_parity import (
    EXACT,
    INCOMPATIBLE,
    MISSING,
    build_hitter_feature_parity_report,
    hitter_parity_is_sufficient_for_inference,
    summarize_hitter_parity,
)
from historical_models.hitter_v1.features import AFTER_LINEUP_FEATURE_COLUMNS


def test_parity_report_has_one_row_per_feature_column():
    rows = build_hitter_feature_parity_report()
    assert [r.feature for r in rows] == AFTER_LINEUP_FEATURE_COLUMNS


def test_parity_report_has_no_incompatible_features():
    rows = build_hitter_feature_parity_report()
    incompatible = [r for r in rows if r.parity_status == INCOMPATIBLE]
    assert incompatible == [], f"Unexpected INCOMPATIBLE features: {[r.feature for r in incompatible]}"


def test_parity_report_marks_weather_family_as_exact_after_m32_7a_live_mapping():
    """M32.7A: weather is now mapped from the real, already-persisted
    Game Environment snapshot (see big_money_ml.live_hitter_features::
    _map_weather_features) -- EXACT, same field-rename-only transformation
    discipline as every other EXACT family, not MISSING/fabricated."""
    rows = build_hitter_feature_parity_report()
    by_column = {r.feature: r for r in rows}
    for col in ("weather_temperature_f", "weather_wind_speed_mph", "weather_wind_direction_deg", "weather_precipitation", "weather_humidity_pct", "weather_available"):
        assert by_column[col].parity_status == EXACT


def test_parity_report_marks_venue_roof_type_as_exact_despite_weather_family_grouping():
    rows = build_hitter_feature_parity_report()
    by_column = {r.feature: r for r in rows}
    assert by_column["venue_roof_type"].parity_status == EXACT


def test_parity_report_marks_rolling_statcast_platoon_and_opposing_pitcher_families_exact():
    rows = build_hitter_feature_parity_report()
    by_column = {r.feature: r for r in rows}
    assert by_column["rolling_ops_30d"].parity_status == EXACT
    assert by_column["statcast_hard_hit_rate_30d"].parity_status == EXACT
    assert by_column["platoon_vs_lhp_woba"].parity_status == EXACT
    assert by_column["opposing_starting_pitcher_hand"].parity_status == EXACT
    assert by_column["opposing_pitcher_era_season"].parity_status == EXACT
    assert by_column["opposing_pitcher_k_pct_season"].parity_status == EXACT


def test_parity_report_marks_batting_order_actual_exact():
    """The one AFTER_LINEUP-only feature -- must be EXACT (sourced from
    research_output/<date>/batters.json's real posted-lineup field), not
    MISSING or COMPATIBLE, since it's only ever requested once a lineup
    has genuinely posted (see eligible_hitters.py's gating)."""
    rows = build_hitter_feature_parity_report()
    by_column = {r.feature: r for r in rows}
    assert by_column["batting_order_actual"].parity_status == EXACT


def test_summarize_parity_counts_are_internally_consistent():
    rows = build_hitter_feature_parity_report()
    summary = summarize_hitter_parity(rows)
    assert summary["total_expected_features"] == len(AFTER_LINEUP_FEATURE_COLUMNS)
    assert (
        summary["exact_count"] + summary["compatible_count"] + summary["missing_count"] + summary["incompatible_count"]
        == summary["total_expected_features"]
    )
    assert len(summary["missing_features"]) == summary["missing_count"]
    assert len(summary["incompatible_features"]) == summary["incompatible_count"]


def test_parity_is_sufficient_for_inference_when_no_incompatible_features():
    rows = build_hitter_feature_parity_report()
    summary = summarize_hitter_parity(rows)
    assert hitter_parity_is_sufficient_for_inference(summary) is True


def test_parity_is_sufficient_for_inference_is_false_when_any_incompatible():
    summary = {"incompatible_count": 1}
    assert hitter_parity_is_sufficient_for_inference(summary) is False
