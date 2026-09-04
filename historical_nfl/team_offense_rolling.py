"""NFL M11 -- rolling team-offense features, same leakage discipline as
historical_nfl/dst_rolling.py (a Week W feature may only read
NflTeamOffenseRecord rows with week < W). Used to attach a DST row's
UPCOMING OPPONENT's own trailing offensive form as real pre-game
context."""

from typing import Dict, List, Optional

from historical_nfl.team_offense_models import NflTeamOffenseRecord

TEAM_OFFENSE_ROLLING_FIELDS = ("points_scored", "total_yards", "turnovers", "sacks_allowed", "pass_attempts", "rush_attempts")
DEFAULT_WINDOWS = (1, 3, 5)


def _team_weeks_before(records: List[NflTeamOffenseRecord], team: str, as_of_week: int) -> Dict[int, NflTeamOffenseRecord]:
    result: Dict[int, NflTeamOffenseRecord] = {}
    for r in records:
        if r.team != team or r.week >= as_of_week:
            continue
        result.setdefault(r.week, r)
    return result


def compute_team_offense_rolling_features(
    records: List[NflTeamOffenseRecord], team: str, as_of_week: int, windows=DEFAULT_WINDOWS, prefix: str = "opponent_",
) -> Dict[str, Optional[float]]:
    weeks_before = _team_weeks_before(records, team, as_of_week)
    features: Dict[str, Optional[float]] = {}
    for window in windows:
        lo = as_of_week - window
        for field in TEAM_OFFENSE_ROLLING_FIELDS:
            values = []
            for week in range(lo, as_of_week):
                record = weeks_before.get(week)
                if record is None:
                    continue
                value = getattr(record, field)
                if value is not None:
                    values.append(value)
            features[f"{prefix}{field}_mean_last{window}"] = round(sum(values) / len(values), 4) if values else None
    features[f"{prefix}weeks_of_history"] = len(weeks_before)
    return features
