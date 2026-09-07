"""NFL M9 -- rolling DST features, same leakage discipline as
historical_nfl/usage_rolling.py (a Week W feature may only read
NflDstUsageRecord rows with week < W), scoped to the M8 DST fields."""

from typing import Dict, List, Optional

from historical_nfl.dst_usage_models import NflDstUsageRecord

DST_ROLLING_FIELDS = ("sacks", "interceptions", "defensive_tds", "points_allowed", "yards_allowed")
DEFAULT_WINDOWS = (1, 3, 5)


def _team_weeks_before(records: List[NflDstUsageRecord], team: str, as_of_week: int) -> Dict[int, NflDstUsageRecord]:
    result: Dict[int, NflDstUsageRecord] = {}
    for r in records:
        if r.team != team or r.week >= as_of_week:
            continue
        result.setdefault(r.week, r)
    return result


def compute_dst_rolling_features(records: List[NflDstUsageRecord], team: str, as_of_week: int, windows=DEFAULT_WINDOWS) -> Dict[str, Optional[float]]:
    weeks_before = _team_weeks_before(records, team, as_of_week)
    features: Dict[str, Optional[float]] = {}
    for window in windows:
        lo = as_of_week - window
        for field in DST_ROLLING_FIELDS:
            values = []
            for week in range(lo, as_of_week):
                record = weeks_before.get(week)
                if record is None:
                    continue
                value = getattr(record, field)
                if value is not None:
                    values.append(value)
            features[f"{field}_mean_last{window}"] = round(sum(values) / len(values), 4) if values else None
    features["weeks_of_history"] = len(weeks_before)
    return features
