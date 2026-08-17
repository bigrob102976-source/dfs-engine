from config import native_projection_config as cfg
from native_projections.models import InputCoverage, NativePlayerProjection
from native_projections.validation import validate_projection


def make_projection(**overrides):
    defaults = dict(
        player_id="X1", name="Test", team="AAA", player_type="hitter",
        native_projection=8.0, native_ceiling=14.0, native_floor=3.0,
        confidence=70.0, variance=10.0,
        input_coverage=InputCoverage(fields_available=8, fields_total=10, missing_fields=[]),
    )
    defaults.update(overrides)
    return NativePlayerProjection(**defaults)


def test_no_warnings_for_a_normal_projection():
    proj = make_projection()
    warnings = validate_projection(proj, season_opportunities=450)
    assert warnings == []


def test_suspicious_high_hitter_projection_flagged():
    proj = make_projection(native_projection=30.0, native_ceiling=40.0, native_floor=20.0)
    warnings = validate_projection(proj, season_opportunities=450)
    assert any("suspicious" in w.lower() for w in warnings)


def test_suspicious_high_pitcher_projection_flagged():
    proj = make_projection(player_type="pitcher", native_projection=50.0, native_ceiling=60.0, native_floor=40.0)
    warnings = validate_projection(proj, season_opportunities=600)
    assert any("suspicious" in w.lower() for w in warnings)


def test_hitter_projection_under_pitcher_threshold_not_flagged():
    # 30 points would be suspicious for a hitter but under the pitcher threshold --
    # confirms the two thresholds are genuinely separate.
    proj = make_projection(player_type="pitcher", native_projection=30.0, native_ceiling=40.0, native_floor=20.0)
    warnings = validate_projection(proj, season_opportunities=600)
    assert not any("suspicious" in w.lower() for w in warnings)


def test_negative_projection_flagged():
    proj = make_projection(native_projection=-2.0, native_ceiling=3.0, native_floor=0.0)
    warnings = validate_projection(proj, season_opportunities=450)
    assert any("negative" in w.lower() for w in warnings)


def test_ceiling_below_projection_flagged():
    proj = make_projection(native_projection=8.0, native_ceiling=5.0, native_floor=3.0)
    warnings = validate_projection(proj, season_opportunities=450)
    assert any("ceiling" in w.lower() and "below" in w.lower() for w in warnings)


def test_floor_above_projection_flagged():
    proj = make_projection(native_projection=8.0, native_ceiling=14.0, native_floor=9.0)
    warnings = validate_projection(proj, season_opportunities=450)
    assert any("floor" in w.lower() and "above" in w.lower() for w in warnings)


def test_tiny_sample_elite_flagged():
    proj = make_projection(native_projection=20.0, native_ceiling=30.0, native_floor=10.0)
    warnings = validate_projection(proj, season_opportunities=8)
    assert any("tiny-sample-elite" in w.lower() for w in warnings)


def test_tiny_sample_non_elite_not_flagged_as_elite():
    proj = make_projection(native_projection=3.0, native_ceiling=6.0, native_floor=1.0)
    warnings = validate_projection(proj, season_opportunities=8)
    assert not any("tiny-sample-elite" in w.lower() for w in warnings)


def test_low_coverage_flagged():
    proj = make_projection(input_coverage=InputCoverage(fields_available=1, fields_total=10, missing_fields=["a"]))
    warnings = validate_projection(proj, season_opportunities=450)
    assert any("low input data coverage" in w.lower() for w in warnings)


def test_high_coverage_not_flagged():
    proj = make_projection(input_coverage=InputCoverage(fields_available=9, fields_total=10, missing_fields=[]))
    warnings = validate_projection(proj, season_opportunities=450)
    assert not any("low input data coverage" in w.lower() for w in warnings)


def test_none_season_opportunities_does_not_crash():
    proj = make_projection()
    warnings = validate_projection(proj, season_opportunities=None)
    assert isinstance(warnings, list)
