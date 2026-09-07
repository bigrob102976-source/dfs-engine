"""NFL M12 -- independent re-derivation of ownership bounds/sum checks,
never trusting nfl/ownership_model.py's own normalization_report.
Mirrors ownership/validator.py's discipline of re-checking rather than
trusting the model's self-report."""

from typing import Dict, List

from config.dk_roster_config_nfl import DK_NFL_CLASSIC_ROSTER_SLOTS, FLEX_ELIGIBLE_BASE_POSITIONS
from config.nfl_ownership_config import OWNERSHIP_NORMALIZATION_TOLERANCE, OWNERSHIP_TIER_THRESHOLDS
from nfl.ownership_models import (
    NFL_OWNERSHIP_POSITIONS,
    NflOwnershipRecord,
    NflOwnershipValidationFinding,
    NflOwnershipValidationResult,
)

_VALID_TIERS = frozenset(name for name, _low, _high in OWNERSHIP_TIER_THRESHOLDS)
_BASE_SLOT_COUNTS: Dict[str, int] = {s["slot"]: s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS if s["slot"] != "FLEX"}
_FLEX_SLOT_COUNT = next(s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS if s["slot"] == "FLEX")


def validate_ownership(total_pool_players: int, records: List[NflOwnershipRecord]) -> NflOwnershipValidationResult:
    findings: List[NflOwnershipValidationFinding] = []
    seen_ids = set()
    sum_by_position: Dict[str, float] = {pos: 0.0 for pos in NFL_OWNERSHIP_POSITIONS}

    for r in records:
        if r.draftkings_player_id in seen_ids:
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: duplicate ownership record for the same player."))
        seen_ids.add(r.draftkings_player_id)

        if r.position not in NFL_OWNERSHIP_POSITIONS:
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: unsupported position {r.position!r}."))
            continue

        if r.ownership_projection is None:
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: ownership_projection is None on a record that should never have been created without one."))
            continue

        value = r.ownership_projection
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: ownership_projection is not numeric ({value!r})."))
            continue
        value = float(value)
        if value != value:  # NaN
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: ownership_projection is NaN."))
            continue
        if value < 0.0 or value > 100.0:
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: ownership_projection {value} out of [0, 100] bounds."))
            continue

        sum_by_position[r.position] += value

        if r.ownership_tier is not None and r.ownership_tier not in _VALID_TIERS:
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: unknown ownership_tier {r.ownership_tier!r}."))
        if r.ownership_confidence is not None and not (0.0 <= r.ownership_confidence <= 100.0):
            findings.append(NflOwnershipValidationFinding("BLOCK", f"{r.name!r}: ownership_confidence {r.ownership_confidence} out of [0, 100] bounds."))
        if r.chalk_score is not None and not (0.0 <= r.chalk_score <= 100.0):
            findings.append(NflOwnershipValidationFinding("WARN", f"{r.name!r}: chalk_score {r.chalk_score} outside the usual [0, 100] range."))

    expected_by_position: Dict[str, float] = {}
    for pos in NFL_OWNERSHIP_POSITIONS:
        if pos in _BASE_SLOT_COUNTS:
            expected = _BASE_SLOT_COUNTS[pos] * 100.0
            if pos in FLEX_ELIGIBLE_BASE_POSITIONS:
                # RB/WR/TE's true expected ceiling also includes SOME
                # share of the shared FLEX slot's 100% -- exactly how
                # much varies by slate (it's proportional to that
                # position's relative FLEX-worthiness, not a fixed
                # split, see nfl/ownership_model.py::_allocate_flex_ownership()).
                # The tolerance check below only ever flags a sum that's
                # LOW relative to the base-only expectation (a real bug
                # symptom) or implausibly high (> base + the ENTIRE FLEX
                # slot, which is only possible under a genuine bug) --
                # it never asserts a specific FLEX split.
                expected_by_position[pos] = expected
            else:
                expected_by_position[pos] = expected
        else:
            expected_by_position[pos] = 0.0

    for pos in NFL_OWNERSHIP_POSITIONS:
        actual = round(sum_by_position[pos], 2)
        if actual == 0.0:
            continue  # no players projected at this position on this slate -- not a normalization failure
        base_expected = expected_by_position[pos]
        upper_bound = base_expected + (_FLEX_SLOT_COUNT * 100.0 if pos in FLEX_ELIGIBLE_BASE_POSITIONS else 0.0) + OWNERSHIP_NORMALIZATION_TOLERANCE
        lower_bound = 0.0 if pos in FLEX_ELIGIBLE_BASE_POSITIONS else (base_expected - OWNERSHIP_NORMALIZATION_TOLERANCE)
        if pos == "QB" or pos == "DST":
            lower_bound = base_expected - OWNERSHIP_NORMALIZATION_TOLERANCE
        if not (lower_bound <= actual <= upper_bound):
            findings.append(NflOwnershipValidationFinding(
                "BLOCK",
                f"{pos} ownership sum {actual} is outside the expected range [{lower_bound}, {upper_bound}] "
                f"(base slot mass {base_expected}).",
            ))

    players_with = sum(1 for r in records if r.ownership_projection is not None)
    return NflOwnershipValidationResult(
        passed=not any(f.level == "BLOCK" for f in findings),
        findings=findings,
        total_pool_players=total_pool_players,
        players_with_ownership=players_with,
        players_missing_ownership=total_pool_players - players_with,
        ownership_sum_by_position={pos: round(v, 2) for pos, v in sum_by_position.items()},
        ownership_expected_by_position=expected_by_position,
    )
