"""NFL M8 -- reusable rolling-window and season-to-date usage feature
functions for the future Big Money Native NFL projection model.

LEAKAGE INVARIANT (the one rule every function here is built around): a
feature computed "as of week W" may only read NflUsageRecord rows with
week < W. Week W's own row (the outcome being predicted) and every week
after it are never touched -- enforced structurally (a single filter
applied before any aggregation, not a convention callers must remember)
and covered by dedicated leakage tests in
tests/test_historical_nfl_usage_rolling.py.

Two field groups, computed differently (Phase 10's "sum where
meaningful" instruction): count-like real box-score fields get BOTH a
mean and a sum over the window (sum is meaningful -- "targets over the
last 3 weeks" is a real, useful number); share/percentage fields get
only a mean (summing a share across weeks is not a meaningful number).
"""

from typing import Dict, List, Optional

from historical_nfl.usage_models import NflUsageRecord

COUNT_FIELDS = (
    "offensive_snaps", "targets", "receptions", "carries",
    "red_zone_targets", "red_zone_carries", "goal_line_carries",
    "pass_attempts", "completions", "passing_yards", "passing_tds",
    "rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds",
)
SHARE_FIELDS = ("snap_share", "target_share", "reception_share", "carry_share")
ALL_ROLLING_FIELDS = COUNT_FIELDS + SHARE_FIELDS

DEFAULT_WINDOWS = (1, 3, 5)


def _player_weeks_before(records: List[NflUsageRecord], gsis_id: str, as_of_week: int) -> Dict[int, NflUsageRecord]:
    """The leakage boundary: every week < as_of_week for this player,
    keyed by week. A week appearing more than once (a real data-quality
    problem, not expected) keeps the first seen -- never averaged
    silently across duplicates."""
    result: Dict[int, NflUsageRecord] = {}
    for r in records:
        if r.gsis_id != gsis_id or r.week >= as_of_week:
            continue
        result.setdefault(r.week, r)
    return result


def _window_values(weeks_before: Dict[int, NflUsageRecord], as_of_week: int, window: int, field: str) -> List[float]:
    lo = as_of_week - window
    values = []
    for week in range(lo, as_of_week):
        record = weeks_before.get(week)
        if record is None:
            continue
        value = getattr(record, field)
        if value is not None:
            values.append(value)
    return values


def compute_player_rolling_features(
    records: List[NflUsageRecord], gsis_id: str, as_of_week: int, windows=DEFAULT_WINDOWS,
) -> Dict[str, Optional[float]]:
    """Returns a flat {feature_name: value} dict for one player as of
    `as_of_week` (never inclusive of that week). None wherever the
    player has zero real weeks of history in that window -- never 0.0,
    which would be indistinguishable from a real observed zero."""
    weeks_before = _player_weeks_before(records, gsis_id, as_of_week)
    features: Dict[str, Optional[float]] = {}

    for window in windows:
        for field in COUNT_FIELDS:
            values = _window_values(weeks_before, as_of_week, window, field)
            features[f"{field}_sum_last{window}"] = round(sum(values), 4) if values else None
            features[f"{field}_mean_last{window}"] = round(sum(values) / len(values), 4) if values else None
        for field in SHARE_FIELDS:
            values = _window_values(weeks_before, as_of_week, window, field)
            features[f"{field}_mean_last{window}"] = round(sum(values) / len(values), 4) if values else None

    # Simple, explicitly-defined trend: most recent single real week vs.
    # the mean of the prior real history (weeks before that one week),
    # only when both sides have real data. Never a fabricated "0 trend"
    # for a rookie/first-week player with no prior history.
    recent_weeks = sorted(weeks_before.keys())
    if recent_weeks:
        last_real_week = recent_weeks[-1]
        prior_weeks = {w: r for w, r in weeks_before.items() if w < last_real_week}
        for field in COUNT_FIELDS + SHARE_FIELDS:
            last_value = getattr(weeks_before[last_real_week], field)
            prior_values = [getattr(r, field) for r in prior_weeks.values() if getattr(r, field) is not None]
            if last_value is not None and prior_values:
                prior_mean = sum(prior_values) / len(prior_values)
                features[f"{field}_trend_delta"] = round(last_value - prior_mean, 4)
            else:
                features[f"{field}_trend_delta"] = None
    else:
        for field in COUNT_FIELDS + SHARE_FIELDS:
            features[f"{field}_trend_delta"] = None

    features["weeks_of_history"] = len(weeks_before)
    return features


def compute_season_to_date_features(records: List[NflUsageRecord], gsis_id: str, as_of_week: int) -> Dict[str, Optional[float]]:
    """Every real week strictly before `as_of_week` (week 1 through
    as_of_week - 1), never as_of_week itself or later -- same leakage
    boundary as compute_player_rolling_features, unbounded window."""
    weeks_before = _player_weeks_before(records, gsis_id, as_of_week)
    features: Dict[str, Optional[float]] = {}

    for field in COUNT_FIELDS:
        values = [getattr(r, field) for r in weeks_before.values() if getattr(r, field) is not None]
        features[f"{field}_season_sum"] = round(sum(values), 4) if values else None
        features[f"{field}_season_mean"] = round(sum(values) / len(values), 4) if values else None
    for field in SHARE_FIELDS:
        values = [getattr(r, field) for r in weeks_before.values() if getattr(r, field) is not None]
        features[f"{field}_season_mean"] = round(sum(values) / len(values), 4) if values else None

    features["season_weeks_of_history"] = len(weeks_before)
    return features
