"""NFL M11 -- targeted tests for historical_nfl/season_timeline.py's
continuous-week remapping (the core of the season-rollover blending
strategy) and real date/season lookups."""

from historical_nfl.season_timeline import (
    completed_weeks_in_season,
    continuous_week,
    determine_season_week_for_date,
    remap_to_continuous_timeline,
)
from historical_nfl.usage_models import NflUsageRecord


def test_continuous_week_prior_season_ends_at_zero():
    assert continuous_week(season=2025, week=18, reference_season=2026) == 0


def test_continuous_week_current_season_starts_at_one():
    assert continuous_week(season=2026, week=1, reference_season=2026) == 1


def test_continuous_week_is_monotonic_across_season_boundary():
    w_prior_17 = continuous_week(2025, 17, reference_season=2026)
    w_prior_18 = continuous_week(2025, 18, reference_season=2026)
    w_current_1 = continuous_week(2026, 1, reference_season=2026)
    w_current_2 = continuous_week(2026, 2, reference_season=2026)
    assert w_prior_17 < w_prior_18 < w_current_1 < w_current_2
    assert w_prior_18 + 1 == w_current_1  # no gap, no overlap


def _record(season, week, gsis_id="00-1", carries=None):
    return NflUsageRecord(canonical_player_id=None, gsis_id=gsis_id, season=season, week=week, game_id=f"{season}_{week}", team="PHI", opponent="DAL", position="RB", carries=carries)


def test_remap_preserves_season_field_for_display():
    records = [_record(2025, 18, carries=10)]
    remapped = remap_to_continuous_timeline(records, reference_season=2026)
    assert remapped[0].season == 2025  # untouched, for audit/display
    assert remapped[0].week == 0  # continuous timeline value


def test_remap_produces_correct_trailing_window_across_season_boundary():
    """The real point of this whole module: a 3-week rolling window
    evaluated at current-season week 2 should span prior-season weeks
    17-18 plus current week 1 -- exactly Phase 6's "strong prior-season
    weight + Week 1" behavior, using the EXISTING rolling function
    completely unmodified."""
    from historical_nfl.usage_rolling import compute_player_rolling_features

    records = [
        _record(2025, 16, carries=100),  # outside the 3-week window (continuous week -2)
        _record(2025, 17, carries=10),   # continuous week -1
        _record(2025, 18, carries=20),   # continuous week 0
        _record(2026, 1, carries=30),    # continuous week 1
    ]
    remapped = remap_to_continuous_timeline(records, reference_season=2026)
    as_of = continuous_week(2026, 2, reference_season=2026)  # predicting current week 2
    features = compute_player_rolling_features(remapped, "00-1", as_of_week=as_of, windows=(3,))
    assert features["carries_mean_last3"] == 20.0  # mean(10, 20, 30), week 16's 100 correctly excluded


def test_determine_season_week_for_real_date():
    season, week = determine_season_week_for_date("2025-09-04")
    assert season == 2025
    assert week == 1


def test_completed_weeks_2025_is_full_season():
    weeks = completed_weeks_in_season(2025)
    assert weeks == list(range(1, 19))


def test_completed_weeks_2026_is_empty_before_season_starts():
    weeks = completed_weeks_in_season(2026)
    assert weeks == []
