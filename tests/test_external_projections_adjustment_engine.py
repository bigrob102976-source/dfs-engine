from config.adjustment_config import BIG_MONEY_ADJUSTMENT_VERSION
from external_projections.adjustment_engine import (
    apply_adjustment,
    build_adjusted_records,
    compute_signals,
    confidence_adjustment_cap,
)
from external_projections.models import PlayerProjectionRecord, ProjectionMergeResult


def _batter_research(**overrides):
    base = {
        "player_id": "h1", "name": "Test Hitter", "team": "BOS", "confidence": 80.0,
        "trend_metrics": {}, "opposing_pitcher": {},
    }
    base.update(overrides)
    return base


def _pitcher_research(**overrides):
    base = {
        "player_id": "p1", "name": "Test Pitcher", "team": "TOR", "confidence": 80.0,
        "trend_metrics": {}, "opponent_stats": {},
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------------------
# Signal detection
# ----------------------------------------------------------------------------


def test_batter_positive_hard_hit_trend_fires():
    record = _batter_research(trend_metrics={"hard_hit_trend": 5.0})
    factors = compute_signals("hitter", record)
    assert any(f.factor == "recent_hard_hit_trend" and f.delta == 0.4 for f in factors)
    assert any("positive recent hard-hit trend" in f.reason for f in factors)


def test_batter_negative_strikeout_trend_fires_matching_milestone_example_wording():
    record = _batter_research(trend_metrics={"strikeout_rate_trend": -5.0})
    factors = compute_signals("hitter", record)
    assert any(f.delta == -0.2 and "elevated recent strikeout risk" in f.reason for f in factors)


def test_batter_favorable_opposing_pitcher_fires():
    record = _batter_research(opposing_pitcher={"xwoba_allowed": 0.350})
    factors = compute_signals("hitter", record)
    assert any(f.factor == "opposing_pitcher_quality" and f.delta == 0.3 for f in factors)


def test_missing_signal_field_never_fires():
    record = _batter_research(trend_metrics={"hard_hit_trend": None})
    factors = compute_signals("hitter", record)
    assert factors == []


def test_signal_within_dead_zone_does_not_fire():
    record = _batter_research(trend_metrics={"hard_hit_trend": 0.5})  # below the 2.0 threshold
    factors = compute_signals("hitter", record)
    assert factors == []


def test_pitcher_velocity_trend_fires():
    record = _pitcher_research(trend_metrics={"velocity_trend": 1.0})
    factors = compute_signals("pitcher", record)
    assert any(f.factor == "velocity_trend" and f.delta == 0.3 for f in factors)


def test_pitcher_favorable_matchup_fires():
    record = _pitcher_research(opponent_stats={"strikeout_percent": 26.0})
    factors = compute_signals("pitcher", record)
    assert any(f.factor == "opponent_matchup" and f.delta == 0.3 for f in factors)


# ----------------------------------------------------------------------------
# apply_adjustment: caps, direction, reasons
# ----------------------------------------------------------------------------


def test_matches_the_milestone_worked_example():
    """external_projection: 10.2; +0.4 hard-hit, +0.3 matchup, -0.2
    strikeout risk -> adjusted_projection: 10.7."""
    record = _batter_research(confidence=90.0, trend_metrics={"hard_hit_trend": 5.0, "strikeout_rate_trend": -5.0}, opposing_pitcher={"xwoba_allowed": 0.350})
    factors = compute_signals("hitter", record)
    assert round(sum(f.delta for f in factors), 2) == 0.5  # 0.4 + 0.3 - 0.2
    result = apply_adjustment(10.2, 18.0, 4.0, factors, 90.0)
    assert result["adjusted_projection"] == 10.7
    assert result["capped"] is False


def test_positive_adjustment_increases_projection():
    factors_delta = compute_signals("hitter", _batter_research(trend_metrics={"hard_hit_trend": 5.0}))
    result = apply_adjustment(10.0, None, None, factors_delta, 90.0)
    assert result["adjustment_delta"] > 0
    assert result["adjusted_projection"] > 10.0


def test_negative_adjustment_decreases_projection():
    factors = compute_signals("hitter", _batter_research(trend_metrics={"hard_hit_trend": -5.0}))
    result = apply_adjustment(10.0, None, None, factors, 90.0)
    assert result["adjustment_delta"] < 0
    assert result["adjusted_projection"] < 10.0


def test_max_positive_adjustment_percent_cap_enforced():
    # Every batter signal firing positive at once, high confidence, on a
    # LOW baseline projection (so the raw point sum is a large percent of
    # it) -- must never exceed the absolute 15% cap even though the raw
    # sum would (1.4 points / 5.0 baseline = 28% uncapped).
    record = _batter_research(confidence=95.0, trend_metrics={
        "hard_hit_trend": 10.0, "xwoba_trend": 0.05, "barrel_trend": 5.0, "strikeout_rate_trend": 10.0,
    }, opposing_pitcher={"xwoba_allowed": 0.400})
    factors = compute_signals("hitter", record)
    result = apply_adjustment(5.0, None, None, factors, 95.0)
    assert result["adjustment_percent"] <= 15.0
    assert result["capped"] is True


def test_max_negative_adjustment_percent_cap_enforced():
    record = _batter_research(confidence=95.0, trend_metrics={
        "hard_hit_trend": -10.0, "xwoba_trend": -0.05, "barrel_trend": -5.0, "strikeout_rate_trend": -10.0,
    }, opposing_pitcher={"xwoba_allowed": 0.200})
    factors = compute_signals("hitter", record)
    result = apply_adjustment(5.0, None, None, factors, 95.0)
    assert result["adjustment_percent"] >= -15.0
    assert result["capped"] is True


def test_low_confidence_caps_at_5_percent_even_with_many_signals():
    record = _batter_research(confidence=10.0, trend_metrics={
        "hard_hit_trend": 10.0, "xwoba_trend": 0.05, "barrel_trend": 5.0, "strikeout_rate_trend": 10.0,
    }, opposing_pitcher={"xwoba_allowed": 0.400})
    factors = compute_signals("hitter", record)
    result = apply_adjustment(10.0, None, None, factors, 10.0)
    assert abs(result["adjustment_percent"]) <= 5.0
    assert result["capped"] is True


def test_confidence_adjustment_cap_bands():
    assert confidence_adjustment_cap(90.0) == 15.0
    assert confidence_adjustment_cap(70.0) == 15.0
    assert confidence_adjustment_cap(50.0) == 10.0
    assert confidence_adjustment_cap(40.0) == 10.0
    assert confidence_adjustment_cap(20.0) == 5.0
    assert confidence_adjustment_cap(0.0) == 5.0
    assert confidence_adjustment_cap(None) == 5.0


def test_zero_signals_means_no_adjustment():
    result = apply_adjustment(10.0, 18.0, 4.0, [], 90.0)
    assert result["adjustment_delta"] == 0.0
    assert result["adjusted_projection"] == 10.0
    assert result["capped"] is False


def test_ceiling_and_floor_move_proportionally_to_projection():
    factors = compute_signals("hitter", _batter_research(trend_metrics={"hard_hit_trend": 5.0}))
    result = apply_adjustment(10.0, 20.0, 5.0, factors, 90.0)
    projection_ratio = result["adjusted_projection"] / 10.0
    assert round(result["adjusted_ceiling"] / 20.0, 3) == round(projection_ratio, 3)
    assert round(result["adjusted_floor"] / 5.0, 3) == round(projection_ratio, 3)


def test_zero_external_projection_is_a_safe_noop():
    result = apply_adjustment(0.0, 0.0, 0.0, [], 90.0)
    assert result["adjusted_projection"] == 0.0
    assert result["adjustment_delta"] == 0.0


def test_none_external_projection_is_a_safe_noop():
    result = apply_adjustment(None, None, None, [], 90.0)
    assert result["adjusted_projection"] is None


# ----------------------------------------------------------------------------
# build_adjusted_records: end-to-end, preservation guarantees
# ----------------------------------------------------------------------------


def _merge_result_for(record: PlayerProjectionRecord) -> ProjectionMergeResult:
    return ProjectionMergeResult(records=[record])


def test_build_adjusted_records_preserves_independent_and_external_values():
    record = PlayerProjectionRecord(
        independent_player_id="h1", name="Test Hitter", team="BOS", player_type="hitter",
        external_player_id="mock-ext-h1", external_projection=10.2, external_ceiling=18.0, external_floor=4.0,
        external_provider="MOCK EXTERNAL PROJECTIONS", external_provider_timestamp="2026-08-11T18:00:00Z",
        independent_projection=9.5, independent_ceiling=16.0, independent_floor=3.5,
    )
    research_by_id = {"h1": _batter_research(confidence=90.0, trend_metrics={"hard_hit_trend": 5.0})}
    [adjusted] = build_adjusted_records(_merge_result_for(record), research_by_id)

    assert adjusted.independent_projection == 9.5
    assert adjusted.independent_ceiling == 16.0
    assert adjusted.independent_floor == 3.5
    assert adjusted.external_projection == 10.2
    assert adjusted.external_ceiling == 18.0
    assert adjusted.external_floor == 4.0
    assert adjusted.adjusted_projection is not None
    assert adjusted.adjusted_projection != adjusted.external_projection


def test_build_adjusted_records_never_mutates_input_record():
    record = PlayerProjectionRecord(
        independent_player_id="h1", name="Test Hitter", team="BOS", player_type="hitter",
        external_projection=10.0, independent_projection=9.0,
    )
    build_adjusted_records(_merge_result_for(record), {"h1": _batter_research(trend_metrics={"hard_hit_trend": 5.0})})
    assert record.adjusted_projection is None  # the ORIGINAL record object is untouched


def test_build_adjusted_records_reasons_and_version_present():
    record = PlayerProjectionRecord(
        independent_player_id="h1", name="Test Hitter", team="BOS", player_type="hitter",
        external_projection=10.0, independent_projection=9.0,
    )
    [adjusted] = build_adjusted_records(_merge_result_for(record), {"h1": _batter_research(trend_metrics={"hard_hit_trend": 5.0})})
    assert adjusted.adjustment_reasons == ["positive recent hard-hit trend"]
    assert len(adjusted.adjustments) == 1
    assert adjusted.adjustments[0].factor == "recent_hard_hit_trend"
    assert BIG_MONEY_ADJUSTMENT_VERSION == "0.1.0"


def test_build_adjusted_records_leaves_adjusted_none_without_research_data():
    record = PlayerProjectionRecord(
        independent_player_id="h1", name="Test Hitter", team="BOS", player_type="hitter",
        external_projection=10.0, independent_projection=9.0,
    )
    [adjusted] = build_adjusted_records(_merge_result_for(record), {})  # no research record for h1
    assert adjusted.adjusted_projection is None
    assert adjusted.adjustments == []


def test_build_adjusted_records_leaves_adjusted_none_without_external_baseline():
    record = PlayerProjectionRecord(
        independent_player_id="h1", name="Test Hitter", team="BOS", player_type="hitter",
        external_projection=None, independent_projection=9.0,
    )
    [adjusted] = build_adjusted_records(_merge_result_for(record), {"h1": _batter_research()})
    assert adjusted.adjusted_projection is None
