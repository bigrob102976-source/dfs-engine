"""Leverage score: a transparent comparison of player quality vs.
projected popularity. Deliberately NOT called "optimal_leverage" -- no
slate simulation has been run, so this is a percentile-difference proxy,
not a modeled optimal-lineup rate (see the milestone's explicit naming
instruction).
"""

from typing import List

from config.ownership_config import LEVERAGE_TAG_THRESHOLDS


def compute_quality_percentile(projection_percentile: float, ceiling_percentile: float, overall_score_percentile: float) -> float:
    return (projection_percentile + ceiling_percentile + overall_score_percentile) / 3.0


def compute_leverage_score(quality_percentile: float, ownership_percentile: float) -> float:
    """quality percentile minus ownership percentile -- positive means
    "better than its ownership suggests" (roughly [-100, 100])."""
    return quality_percentile - ownership_percentile


def assign_leverage_tags(
    leverage_score: float, projected_ownership: float, ceiling_percentile: float,
    quality_percentile: float, ownership_tier: str,
) -> List[str]:
    t = LEVERAGE_TAG_THRESHOLDS
    tags: List[str] = []

    if leverage_score >= t["elite_leverage"]:
        tags.append("elite_leverage")
    elif leverage_score >= t["positive_leverage"]:
        tags.append("positive_leverage")
    elif leverage_score <= t["negative_leverage"]:
        tags.append("negative_leverage")

    chalk_tiers = ("high", "very_high") if t["chalk_min_ownership_tier"] == "high" else ("very_high",)
    if ownership_tier in chalk_tiers:
        tags.append("chalk")

    if (projected_ownership <= t["low_owned_ceiling_max_ownership"]
            and ceiling_percentile >= t["low_owned_ceiling_min_ceiling_percentile"]):
        tags.append("low_owned_ceiling")

    if (projected_ownership <= t["contrarian_max_ownership"]
            and quality_percentile >= t["contrarian_min_quality_percentile"]):
        tags.append("contrarian")

    return tags
