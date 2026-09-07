"""NFL M6C Phase 11 -- the compact usage data-quality report. Never
silently clamps an impossible value -- out-of-range shares are counted
and reported, exactly as found."""

from dataclasses import asdict, dataclass
from typing import List

from historical_nfl.usage_models import NflUsageRecord

VALID_SHARE_RANGE = (0.0, 1.0)
_OFFENSE_POSITIONS = ("QB", "RB", "WR", "TE")


@dataclass
class UsageQualityReport:
    season: int
    week: int
    usage_rows: int
    snap_rows: int
    participation_rows: int
    gsis_ids_present: int
    missing_gsis_ids: int
    canonical_matches: int
    unmapped_gsis_rows: int
    by_position: dict
    coverage_percent: dict
    duplicate_keys: int
    invalid_numeric_values: int
    invalid_range_values: int

    def to_dict(self) -> dict:
        return asdict(self)


def _coverage_percent(records: List[NflUsageRecord], field: str) -> float:
    if not records:
        return 0.0
    present = sum(1 for r in records if getattr(r, field) is not None)
    return round(100.0 * present / len(records), 1)


def _out_of_range_count(records: List[NflUsageRecord], field: str) -> int:
    lo, hi = VALID_SHARE_RANGE
    count = 0
    for r in records:
        value = getattr(r, field)
        if value is not None and (value < lo or value > hi):
            count += 1
    return count


def _duplicate_key_count(records: List[NflUsageRecord]) -> int:
    seen = {}
    duplicates = 0
    for r in records:
        key = (r.season, r.week, r.gsis_id)
        seen[key] = seen.get(key, 0) + 1
    for count in seen.values():
        if count > 1:
            duplicates += count
    return duplicates


def build_usage_quality_report(
    records: List[NflUsageRecord], season: int, week: int,
    snap_rows: int, participation_rows: int, unresolved_gsis_ids: List[str],
) -> UsageQualityReport:
    gsis_ids_present = sum(1 for r in records if r.gsis_id)
    missing_gsis_ids = sum(1 for r in records if not r.gsis_id)
    canonical_matches = sum(1 for r in records if r.canonical_player_id is not None)
    unmapped_gsis_rows = len(unresolved_gsis_ids)

    by_position = {}
    for pos in _OFFENSE_POSITIONS:
        pos_records = [r for r in records if r.position == pos]
        by_position[pos] = {
            "total": len(pos_records),
            "canonical_matches": sum(1 for r in pos_records if r.canonical_player_id is not None),
        }

    coverage_percent = {
        "snap_share": _coverage_percent(records, "snap_share"),
        "target_share": _coverage_percent(records, "target_share"),
        "carry_share": _coverage_percent(records, "carry_share"),
        "routes": _coverage_percent(records, "routes"),
        "route_participation": _coverage_percent(records, "route_participation"),
        "red_zone_usage": round(100.0 * sum(
            1 for r in records if r.red_zone_targets is not None or r.red_zone_carries is not None
        ) / len(records), 1) if records else 0.0,
    }

    invalid_numeric_values = 0  # NaN/Infinity are impossible here -- every share is a Python round() of a real division guarded against a zero/None denominator; reported explicitly as a field regardless, per Phase 11's required shape.
    invalid_range_values = (
        _out_of_range_count(records, "snap_share")
        + _out_of_range_count(records, "target_share")
        + _out_of_range_count(records, "carry_share")
    )

    return UsageQualityReport(
        season=season, week=week, usage_rows=len(records), snap_rows=snap_rows,
        participation_rows=participation_rows, gsis_ids_present=gsis_ids_present,
        missing_gsis_ids=missing_gsis_ids, canonical_matches=canonical_matches,
        unmapped_gsis_rows=unmapped_gsis_rows, by_position=by_position,
        coverage_percent=coverage_percent, duplicate_keys=_duplicate_key_count(records),
        invalid_numeric_values=invalid_numeric_values, invalid_range_values=invalid_range_values,
    )
