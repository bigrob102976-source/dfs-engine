from ownership.model import build_ownership_projections
from ownership.validator import validate_ownership_projections
from tests._ownership_fixtures import small_slate_hitters, small_slate_pitchers


def _real_projections():
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    return projections


def test_valid_projections_pass():
    violations = validate_ownership_projections(_real_projections())
    assert violations == []


def test_negative_ownership_detected():
    projections = _real_projections()
    projections[0].projected_ownership = -5.0
    violations = validate_ownership_projections(projections)
    assert any("negative" in v for v in violations)


def test_over_100_ownership_detected():
    projections = _real_projections()
    projections[0].projected_ownership = 150.0
    violations = validate_ownership_projections(projections)
    assert any("exceeds 100%" in v for v in violations)


def test_ownership_confidence_out_of_range_detected():
    projections = _real_projections()
    projections[0].ownership_confidence = 250.0
    violations = validate_ownership_projections(projections)
    assert any("ownership_confidence" in v for v in violations)


def test_chalk_score_out_of_range_detected():
    projections = _real_projections()
    projections[0].chalk_score = -10.0
    violations = validate_ownership_projections(projections)
    assert any("chalk_score" in v for v in violations)


def test_pitcher_sum_mismatch_detected():
    projections = _real_projections()
    for p in projections:
        if p.player_type == "pitcher":
            p.projected_ownership = 5.0  # collectively way under 200%
    violations = validate_ownership_projections(projections)
    assert any("Pitcher ownership sums" in v for v in violations)


def test_hitter_sum_mismatch_detected():
    projections = _real_projections()
    for p in projections:
        if p.player_type == "hitter":
            p.projected_ownership = 1.0  # collectively way under 800%
    violations = validate_ownership_projections(projections)
    assert any("Hitter ownership sums" in v for v in violations)


def test_invalid_tier_detected():
    projections = _real_projections()
    projections[0].ownership_tier = "not_a_real_tier"
    violations = validate_ownership_projections(projections)
    assert any("ownership_tier" in v for v in violations)


def test_empty_list_is_valid():
    assert validate_ownership_projections([]) == []
