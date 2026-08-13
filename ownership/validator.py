"""Independent post-hoc validation of an ownership projection run.
Re-derives every check from the raw OwnershipProjection list itself --
never trusts ownership/model.py's own normalization_report, mirroring
optimizer/validator.py's "never assume success implies legality" pattern.
"""

from typing import List

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS, DK_ROSTER_SIZE
from config.ownership_config import OWNERSHIP_NORMALIZATION_TOLERANCE, OWNERSHIP_TIER_THRESHOLDS
from ownership.models import OwnershipProjection


def validate_ownership_projections(projections: List[OwnershipProjection]) -> List[str]:
    violations: List[str] = []

    for p in projections:
        if p.projected_ownership < 0.0:
            violations.append(f"{p.name}: projected_ownership {p.projected_ownership} is negative.")
        if p.projected_ownership > 100.0:
            violations.append(f"{p.name}: projected_ownership {p.projected_ownership} exceeds 100%.")
        if p.ownership_confidence < 0.0 or p.ownership_confidence > 100.0:
            violations.append(f"{p.name}: ownership_confidence {p.ownership_confidence} is out of [0, 100].")
        if p.chalk_score < 0.0 or p.chalk_score > 100.0:
            violations.append(f"{p.name}: chalk_score {p.chalk_score} is out of [0, 100].")

    pitchers = [p for p in projections if p.player_type == "pitcher"]
    hitters = [p for p in projections if p.player_type == "hitter"]

    pitcher_slot_count = next(s["count"] for s in DK_CLASSIC_ROSTER_SLOTS if s["slot"] == "P")
    hitter_slot_count = DK_ROSTER_SIZE - pitcher_slot_count
    expected_pitcher_sum = pitcher_slot_count * 100.0
    expected_hitter_sum = hitter_slot_count * 100.0

    if pitchers:
        pitcher_sum = sum(p.projected_ownership for p in pitchers)
        if abs(pitcher_sum - expected_pitcher_sum) > OWNERSHIP_NORMALIZATION_TOLERANCE:
            violations.append(
                f"Pitcher ownership sums to {pitcher_sum:.2f}, expected ~{expected_pitcher_sum:.1f} "
                f"(tolerance {OWNERSHIP_NORMALIZATION_TOLERANCE})."
            )

    if hitters:
        hitter_sum = sum(h.projected_ownership for h in hitters)
        if abs(hitter_sum - expected_hitter_sum) > OWNERSHIP_NORMALIZATION_TOLERANCE:
            violations.append(
                f"Hitter ownership sums to {hitter_sum:.2f}, expected ~{expected_hitter_sum:.1f} "
                f"(tolerance {OWNERSHIP_NORMALIZATION_TOLERANCE})."
            )

    valid_tiers = {name for name, _low, _high in OWNERSHIP_TIER_THRESHOLDS}
    for p in projections:
        if p.ownership_tier not in valid_tiers:
            violations.append(f"{p.name}: ownership_tier {p.ownership_tier!r} is not one of the configured tiers.")

    return violations
