"""Anti-leakage policy (Milestone 32.0, Part 6). CRITICAL per the
milestone spec -- every function here is a guard, not a suggestion.

POLICY (explicit, enforced programmatically below, not just documented):

  For a target game on date D:
    ALLOWED    -- any stat/observation with an as_of date < D.
    ALLOWED    -- an observation ON date D itself, ONLY if it is
                  chronologically BEFORE the target game's own first
                  pitch AND the caller explicitly opts in via
                  `allow_same_day=True` (e.g. an earlier game of a
                  doubleheader, or a lineup posted that morning). This
                  is opt-in, not the default, because "same day" is the
                  single easiest place to accidentally leak (e.g. a
                  rolling average computed from a full day's games that
                  includes the target game itself).
    FORBIDDEN  -- anything with an as_of date > D.
    FORBIDDEN  -- anything with an as_of date == D UNLESS the above
                  opt-in + before-first-pitch condition holds.
    FORBIDDEN  -- ANY field derived from the target game's own result
                  (actual_* columns must never appear on the FEATURE
                  side of a training row -- they are the label).
    FORBIDDEN  -- season-to-date stats computed from a source that
                  includes games after D (e.g. MLB Stats API's
                  `stats=season` endpoint for the CURRENT season
                  reflects the whole season to date of the query, not
                  to date of the target game -- see this module's
                  `assert_source_as_of` docstring for why season-total
                  endpoints are unsafe for historical training without
                  an explicit as-of cutoff).

This module raises LeakageError rather than silently dropping/clamping
a bad value -- a caller building a training row is expected to catch it
per-row (skip that one row) rather than the whole pipeline silently
producing leaked features.
"""

from dataclasses import dataclass
from typing import List, Optional


class LeakageError(ValueError):
    """Raised when a feature observation would leak future information
    into a historical training row."""


@dataclass
class AsOfCheck:
    target_game_date: str
    observation_date: str
    allow_same_day: bool = False
    observation_is_before_first_pitch: bool = False


def assert_no_leakage(check: AsOfCheck, field_name: str = "") -> None:
    """The single enforcement point every rolling-feature/join function
    in this package must call before accepting an observation. Compares
    ISO date strings lexicographically (safe for YYYY-MM-DD)."""
    label = f" ({field_name})" if field_name else ""
    if check.observation_date > check.target_game_date:
        raise LeakageError(
            f"Leakage{label}: observation_date {check.observation_date!r} is AFTER target game date {check.target_game_date!r}."
        )
    if check.observation_date == check.target_game_date:
        if not check.allow_same_day:
            raise LeakageError(
                f"Leakage{label}: observation_date equals target game date {check.target_game_date!r} but allow_same_day was not set."
            )
        if not check.observation_is_before_first_pitch:
            raise LeakageError(
                f"Leakage{label}: same-day observation on {check.target_game_date!r} was not confirmed to be before the target game's first pitch."
            )


def filter_pregame_observations(observation_dates: List[str], target_game_date: str, allow_same_day: bool = False) -> List[str]:
    """Convenience filter for a list of dates (e.g. a player's own game
    log dates) down to the ones safe to use for a target game -- never
    raises; simply excludes anything not safely pregame. Same-day dates
    are excluded here too unless allow_same_day (and even then, this
    pure date-string filter can't itself confirm before-first-pitch --
    a caller allowing same-day data must separately confirm that via
    assert_no_leakage's observation_is_before_first_pitch)."""
    if allow_same_day:
        return [d for d in observation_dates if d <= target_game_date]
    return [d for d in observation_dates if d < target_game_date]


# Fields that must NEVER appear among a training row's FEATURE columns
# (the "before first pitch" side) -- only on the label/target side. A
# caller assembling a training row should assert none of these keys
# leaked into the feature dict; see historical_mlb/audit.py's
# `check_no_leaked_actuals` for the automated version of this check.
FORBIDDEN_FEATURE_PREFIXES = ("actual_",)


def field_is_leakage_risk(field_name: str) -> bool:
    return any(field_name.startswith(prefix) for prefix in FORBIDDEN_FEATURE_PREFIXES)


def assert_source_as_of(source_description: str, source_covers_through_date: Optional[str], target_game_date: str) -> None:
    """Guards against the specific, easy-to-miss leakage source this
    module's docstring calls out: a "season-to-date" stats endpoint
    queried TODAY reflects the whole season through today, not through
    the historical target game's date. `source_covers_through_date`
    must be the LATEST date the fetched data actually reflects (e.g. a
    game log's own last entry date) -- if it's None (unknown) or later
    than the target date, this raises rather than assuming safety."""
    if source_covers_through_date is None:
        raise LeakageError(
            f"Leakage: {source_description} has no known as-of date, so it cannot be proven safe for target game {target_game_date!r}."
        )
    if source_covers_through_date > target_game_date:
        raise LeakageError(
            f"Leakage: {source_description} covers through {source_covers_through_date!r}, which is after target game date {target_game_date!r}."
        )
