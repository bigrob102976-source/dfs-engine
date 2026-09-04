"""NFL M11 -- maps (season, week) onto one continuous integer timeline
so the EXISTING, already-tested leakage-safe rolling functions
(historical_nfl/usage_rolling.py, dst_rolling.py) can blend prior-season
and current-season history with zero new blending code.

historical_nfl/usage_rolling.py's _player_weeks_before() (and dst_rolling
.py's team equivalent) filter purely on `record.week < as_of_week` --
they never look at `record.season` at all. That means if every record's
`week` field is remapped onto one shared continuous timeline before
being handed to those functions, the SAME trailing-window mechanism
naturally produces exactly Phase 6's requested behavior with no
"blend weight" invented or tuned:

  continuous_week(season, week) = (season - reference_season) * WEEKS_PER_SEASON + week

For reference_season = the CURRENT season and WEEKS_PER_SEASON = 18
(a real, fixed NFL regular-season length, not a guess):
  - prior season week 18 -> continuous week 0
  - prior season week 17 -> continuous week -1
  - current season week 1 -> continuous week 1
  - current season week 4 -> continuous week 4

A 3-week trailing window evaluated as-of current week 2 (continuous
week 2) therefore reads continuous weeks [-1, 0, 1] = prior season's
weeks 17-18 PLUS current week 1 -- automatically "strong prior-season
weight + Week 1" without a single hardcoded blend weight. By current
week 4+, the same 3-week window is entirely inside the current season.
Season-to-date (unbounded window) still correctly accumulates EVERY
real prior week regardless of season, weighted toward whichever season
has more completed weeks purely because there are more real rows from
it -- never an invented multiplier."""

from dataclasses import replace
from typing import List, Optional, Tuple, TypeVar

from historical_nfl import nflverse_client as nc

WEEKS_PER_SEASON = 18  # real, fixed NFL regular-season length (2021-present)

T = TypeVar("T")


def continuous_week(season: int, week: int, reference_season: int) -> int:
    return (season - reference_season) * WEEKS_PER_SEASON + week


def remap_to_continuous_timeline(records: List[T], reference_season: int) -> List[T]:
    """Returns NEW record objects (dataclasses.replace -- never mutates
    the originals, which callers may still need with their real
    season/week intact for display/audit) with `week` overwritten to
    its continuous-timeline value. `season` is left untouched on the
    copy purely for human-readable provenance; every leakage/ordering
    decision downstream uses only the remapped `week`."""
    return [replace(r, week=continuous_week(r.season, r.week, reference_season)) for r in records]


def determine_season_week_for_date(slate_date: str) -> Tuple[int, int]:
    """Real, structural lookup -- never guessed: finds the real NFL
    schedule row whose own `gameday` matches `slate_date` and returns
    its real (season, week). Tries the calendar year implied by
    slate_date first (NFL seasons are named for the year they start in,
    and run into the following January/February), then that year minus
    one (covers a January/February slate_date, which belongs to the
    PRIOR calendar year's season)."""
    year = int(slate_date[:4])
    for candidate_season in (year, year - 1):
        try:
            df, _, _ = nc.fetch_schedules(candidate_season)
        except Exception:  # noqa: BLE001 -- a season with no real schedule yet (e.g. too far future) is a real, expected miss, not an error
            continue
        matches = df.filter(df["gameday"] == slate_date)
        if matches.height > 0:
            return candidate_season, int(matches["week"][0])
    raise ValueError(f"No real NFL schedule game found on {slate_date!r} in season {year} or {year - 1}.")


def completed_weeks_in_season(season: int) -> List[int]:
    """Real weeks of `season` with at least one final score in the real
    schedule -- never assumed from the calendar date alone (a scheduled
    week can be postponed/incomplete)."""
    try:
        df, _, _ = nc.fetch_schedules(season)
    except Exception:  # noqa: BLE001 -- a season with no schedule published yet
        return []
    reg = df.filter(df["game_type"] == "REG")
    completed = reg.filter(reg["home_score"].is_not_null())
    if completed.height == 0:
        return []
    return sorted(completed["week"].unique().to_list())
