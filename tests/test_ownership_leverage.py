from config.ownership_config import LEVERAGE_TAG_THRESHOLDS
from ownership.leverage import assign_leverage_tags, compute_leverage_score, compute_quality_percentile


def test_quality_percentile_is_average_of_three():
    assert compute_quality_percentile(90.0, 80.0, 70.0) == 80.0


def test_leverage_score_positive_when_quality_exceeds_ownership():
    assert compute_leverage_score(quality_percentile=88.0, ownership_percentile=20.0) == 68.0


def test_leverage_score_negative_when_ownership_exceeds_quality():
    assert compute_leverage_score(quality_percentile=30.0, ownership_percentile=90.0) == -60.0


def test_elite_leverage_tag():
    lev = LEVERAGE_TAG_THRESHOLDS["elite_leverage"] + 1
    tags = assign_leverage_tags(lev, projected_ownership=10.0, ceiling_percentile=50.0, quality_percentile=80.0, ownership_tier="low")
    assert "elite_leverage" in tags
    assert "positive_leverage" not in tags


def test_positive_leverage_tag():
    lev = LEVERAGE_TAG_THRESHOLDS["positive_leverage"] + 1
    tags = assign_leverage_tags(lev, projected_ownership=10.0, ceiling_percentile=50.0, quality_percentile=70.0, ownership_tier="low")
    assert "positive_leverage" in tags
    assert "elite_leverage" not in tags


def test_negative_leverage_tag():
    lev = LEVERAGE_TAG_THRESHOLDS["negative_leverage"] - 1
    tags = assign_leverage_tags(lev, projected_ownership=40.0, ceiling_percentile=50.0, quality_percentile=20.0, ownership_tier="very_high")
    assert "negative_leverage" in tags


def test_chalk_tag_for_high_tier():
    tags = assign_leverage_tags(0.0, projected_ownership=25.0, ceiling_percentile=50.0, quality_percentile=50.0, ownership_tier="high")
    assert "chalk" in tags


def test_no_chalk_tag_for_low_tier():
    tags = assign_leverage_tags(0.0, projected_ownership=6.0, ceiling_percentile=50.0, quality_percentile=50.0, ownership_tier="low")
    assert "chalk" not in tags


def test_low_owned_ceiling_tag():
    t = LEVERAGE_TAG_THRESHOLDS
    tags = assign_leverage_tags(
        20.0, projected_ownership=t["low_owned_ceiling_max_ownership"] - 1,
        ceiling_percentile=t["low_owned_ceiling_min_ceiling_percentile"] + 1, quality_percentile=50.0, ownership_tier="low",
    )
    assert "low_owned_ceiling" in tags


def test_contrarian_tag():
    t = LEVERAGE_TAG_THRESHOLDS
    tags = assign_leverage_tags(
        5.0, projected_ownership=t["contrarian_max_ownership"] - 1, ceiling_percentile=50.0,
        quality_percentile=t["contrarian_min_quality_percentile"] + 1, ownership_tier="very_low",
    )
    assert "contrarian" in tags


def test_no_tags_for_neutral_player():
    tags = assign_leverage_tags(0.0, projected_ownership=15.0, ceiling_percentile=50.0, quality_percentile=50.0, ownership_tier="medium")
    assert tags == []
