"""Milestone 32.0 -- historical_mlb/leakage.py. No network calls."""

import pytest

from historical_mlb.leakage import (
    AsOfCheck,
    LeakageError,
    assert_no_leakage,
    assert_source_as_of,
    field_is_leakage_risk,
    filter_pregame_observations,
)


def test_assert_no_leakage_allows_strictly_prior_date():
    assert_no_leakage(AsOfCheck(target_game_date="2025-06-15", observation_date="2025-06-14"))  # must not raise


def test_assert_no_leakage_rejects_future_date():
    with pytest.raises(LeakageError):
        assert_no_leakage(AsOfCheck(target_game_date="2025-06-15", observation_date="2025-06-16"))


def test_assert_no_leakage_rejects_same_day_by_default():
    with pytest.raises(LeakageError):
        assert_no_leakage(AsOfCheck(target_game_date="2025-06-15", observation_date="2025-06-15"))


def test_assert_no_leakage_rejects_same_day_opt_in_without_before_first_pitch_confirmation():
    with pytest.raises(LeakageError):
        assert_no_leakage(AsOfCheck(target_game_date="2025-06-15", observation_date="2025-06-15", allow_same_day=True))


def test_assert_no_leakage_allows_same_day_with_full_opt_in():
    assert_no_leakage(AsOfCheck(
        target_game_date="2025-06-15", observation_date="2025-06-15",
        allow_same_day=True, observation_is_before_first_pitch=True,
    ))  # must not raise


def test_filter_pregame_observations_excludes_target_date_by_default():
    dates = ["2025-06-13", "2025-06-14", "2025-06-15", "2025-06-16"]
    result = filter_pregame_observations(dates, target_game_date="2025-06-15")
    assert result == ["2025-06-13", "2025-06-14"]


def test_filter_pregame_observations_allow_same_day_still_excludes_future():
    dates = ["2025-06-14", "2025-06-15", "2025-06-16"]
    result = filter_pregame_observations(dates, target_game_date="2025-06-15", allow_same_day=True)
    assert result == ["2025-06-14", "2025-06-15"]


def test_field_is_leakage_risk():
    assert field_is_leakage_risk("actual_dk_points") is True
    assert field_is_leakage_risk("rolling_avg_30d") is False


def test_assert_source_as_of_rejects_unknown_coverage():
    with pytest.raises(LeakageError):
        assert_source_as_of("season stats endpoint", None, "2025-06-15")


def test_assert_source_as_of_rejects_coverage_past_target():
    with pytest.raises(LeakageError):
        assert_source_as_of("season stats endpoint", "2025-06-20", "2025-06-15")


def test_assert_source_as_of_allows_coverage_through_target_or_earlier():
    assert_source_as_of("game log", "2025-06-14", "2025-06-15")  # must not raise
