from config.projection_engine_config import PITCHER_ENVIRONMENT_DAMPENING, SIGNAL_WEIGHTS
from projection_engine.models import RawSignal
from projection_engine.weights import apply_weight, blend_confidence, blend_risk, cap_total_adjustment, is_finite_number


def test_apply_weight_multiplies_by_configured_category_weight():
    raw = RawSignal(category="ownership", label="Ownership", raw_delta=1.0, reason="test")
    signal = apply_weight(raw, "hitter")
    assert signal.delta == round(1.0 * SIGNAL_WEIGHTS["ownership"], 3)
    assert signal.weight == SIGNAL_WEIGHTS["ownership"]


def test_weather_dampened_for_pitcher_but_not_hitter():
    raw = RawSignal(category="weather", label="Weather", raw_delta=1.0, reason="test")
    pitcher_signal = apply_weight(raw, "pitcher")
    hitter_signal = apply_weight(raw, "hitter")
    assert pitcher_signal.delta == round(1.0 * SIGNAL_WEIGHTS["weather"] * PITCHER_ENVIRONMENT_DAMPENING, 3)
    assert hitter_signal.delta == round(1.0 * SIGNAL_WEIGHTS["weather"], 3)
    assert abs(pitcher_signal.delta) < abs(hitter_signal.delta)


def test_park_dampened_for_pitcher_matches_weather_dampening_factor():
    raw = RawSignal(category="park", label="Park", raw_delta=1.0, reason="test")
    pitcher_signal = apply_weight(raw, "pitcher")
    undampened = raw.raw_delta * SIGNAL_WEIGHTS["park"]
    assert pitcher_signal.delta == round(undampened * PITCHER_ENVIRONMENT_DAMPENING, 3)


def test_matchup_not_dampened_for_pitcher():
    raw = RawSignal(category="matchup", label="Matchup", raw_delta=1.0, reason="test")
    pitcher_signal = apply_weight(raw, "pitcher")
    assert pitcher_signal.delta == round(1.0 * SIGNAL_WEIGHTS["matchup"], 3)


def test_external_gap_is_capped_after_weighting():
    from config.projection_engine_config import EXTERNAL_GAP_MAX_POINTS

    raw = RawSignal(category="external", label="External Projection", raw_delta=100.0, reason="huge gap")
    signal = apply_weight(raw, "hitter")
    assert signal.delta <= EXTERNAL_GAP_MAX_POINTS
    raw_negative = RawSignal(category="external", label="External Projection", raw_delta=-100.0, reason="huge gap")
    signal_negative = apply_weight(raw_negative, "hitter")
    assert signal_negative.delta >= -EXTERNAL_GAP_MAX_POINTS


# ----------------------------------------------------------------------------
# cap_total_adjustment
# ----------------------------------------------------------------------------


def test_small_adjustment_passes_through_uncapped():
    delta, capped = cap_total_adjustment(0.5, 10.0)
    assert delta == 0.5
    assert capped is False


def test_large_positive_adjustment_is_capped():
    delta, capped = cap_total_adjustment(5.0, 10.0)  # 50% > MAX_TOTAL_ADJUSTMENT_PERCENT (20%)
    assert capped is True
    assert delta == 2.0  # 20% of 10.0


def test_large_negative_adjustment_is_capped():
    delta, capped = cap_total_adjustment(-5.0, 10.0)
    assert capped is True
    assert delta == -2.0


def test_zero_or_missing_baseline_never_divides_by_zero():
    delta, capped = cap_total_adjustment(5.0, None)
    assert delta == 5.0
    assert capped is False
    delta, capped = cap_total_adjustment(5.0, 0.0)
    assert delta == 5.0
    assert capped is False


# ----------------------------------------------------------------------------
# blend_confidence
# ----------------------------------------------------------------------------


def test_blend_confidence_all_present():
    blended = blend_confidence(80.0, 60.0, 90.0)
    assert 60.0 < blended < 90.0


def test_blend_confidence_renormalizes_over_available_inputs():
    only_research = blend_confidence(80.0, None, None)
    assert only_research == 80.0


def test_blend_confidence_all_missing_returns_none():
    assert blend_confidence(None, None, None) is None


def test_blend_confidence_clamped_0_100():
    blended = blend_confidence(150.0, None, None)
    assert blended <= 100.0


# ----------------------------------------------------------------------------
# blend_risk
# ----------------------------------------------------------------------------


def test_blend_risk_missing_base_returns_none():
    assert blend_risk(None, [], None, None) is None


def test_blend_risk_weather_risk_conclusion_bumps_risk():
    weather_analysis = {"conclusions": [{"code": "rain_delay_risk", "favors": "risk"}]}
    risk = blend_risk(30.0, [], weather_analysis, None)
    assert risk > 30.0


def test_blend_risk_large_adjustment_bumps_risk():
    risk = blend_risk(30.0, [], None, 15.0)  # above RISK_LARGE_ADJUSTMENT_THRESHOLD_PERCENT
    assert risk > 30.0


def test_blend_risk_clamped_0_100():
    weather_analysis = {"conclusions": [{"code": "rain_delay_risk", "favors": "risk"}, {"code": "postponement_risk", "favors": "risk"}]}
    risk = blend_risk(98.0, [], weather_analysis, 50.0)
    assert risk <= 100.0


# ----------------------------------------------------------------------------
# is_finite_number
# ----------------------------------------------------------------------------


def test_is_finite_number_accepts_real_numbers():
    assert is_finite_number(1.5) is True
    assert is_finite_number(0) is True
    assert is_finite_number(-3) is True


def test_is_finite_number_rejects_none_nan_inf_bool():
    assert is_finite_number(None) is False
    assert is_finite_number(float("nan")) is False
    assert is_finite_number(float("inf")) is False
    assert is_finite_number(float("-inf")) is False
    assert is_finite_number(True) is False
    assert is_finite_number("5") is False
