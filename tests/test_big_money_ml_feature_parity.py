"""Milestone 32.2B -- training/live feature parity report tests."""

from big_money_ml.feature_parity import (
    EXACT,
    INCOMPATIBLE,
    MISSING,
    build_feature_parity_report,
    parity_is_sufficient_for_inference,
    summarize_parity,
)
from historical_models.pitcher_v1.features import FEATURE_COLUMNS


def test_parity_report_has_one_row_per_feature_column():
    rows = build_feature_parity_report()
    assert [r.feature for r in rows] == FEATURE_COLUMNS


def test_parity_report_has_no_incompatible_features():
    rows = build_feature_parity_report()
    incompatible = [r for r in rows if r.parity_status == INCOMPATIBLE]
    assert incompatible == [], f"Unexpected INCOMPATIBLE features: {[r.feature for r in incompatible]}"


def test_parity_report_marks_weather_family_as_missing_not_fabricated():
    rows = build_feature_parity_report()
    by_column = {r.feature: r for r in rows}
    for col in ("weather_temperature_f", "weather_wind_speed_mph", "weather_wind_direction_deg", "weather_precipitation", "weather_humidity_pct", "weather_available"):
        assert by_column[col].parity_status == MISSING


def test_parity_report_marks_venue_roof_type_as_exact_despite_weather_family_grouping():
    """venue_roof_type is grouped under the manifest's "weather" family
    but is a static per-team lookup, always available live -- must not
    inherit the weather family's MISSING status."""
    rows = build_feature_parity_report()
    by_column = {r.feature: r for r in rows}
    assert by_column["venue_roof_type"].parity_status == EXACT


def test_parity_report_marks_rolling_and_statcast_families_exact():
    rows = build_feature_parity_report()
    by_column = {r.feature: r for r in rows}
    assert by_column["rolling_k_pct_30d"].parity_status == EXACT
    assert by_column["statcast_hard_hit_rate_allowed_30d"].parity_status == EXACT
    assert by_column["platoon_vs_lhb_woba_allowed"].parity_status == EXACT
    assert by_column["opponent_k_pct_season"].parity_status == EXACT


def test_summarize_parity_counts_are_internally_consistent():
    rows = build_feature_parity_report()
    summary = summarize_parity(rows)
    assert summary["total_expected_features"] == len(FEATURE_COLUMNS)
    assert (
        summary["exact_count"] + summary["compatible_count"] + summary["missing_count"] + summary["incompatible_count"]
        == summary["total_expected_features"]
    )
    assert len(summary["missing_features"]) == summary["missing_count"]
    assert len(summary["incompatible_features"]) == summary["incompatible_count"]


def test_parity_is_sufficient_for_inference_when_no_incompatible_features():
    rows = build_feature_parity_report()
    summary = summarize_parity(rows)
    assert parity_is_sufficient_for_inference(summary) is True


def test_parity_is_sufficient_for_inference_is_false_when_any_incompatible():
    summary = {"incompatible_count": 1}
    assert parity_is_sufficient_for_inference(summary) is False
