"""NFL M6B -- targeted tests for historical_nfl/identity_position.py."""

import pytest

from historical_nfl.identity_position import is_position_compatible


def test_exact_position_match_is_compatible():
    assert is_position_compatible("QB", "QB") is True
    assert is_position_compatible("RB", "RB") is True
    assert is_position_compatible("WR", "WR") is True
    assert is_position_compatible("TE", "TE") is True


def test_different_position_is_not_compatible():
    assert is_position_compatible("RB", "TE") is False
    assert is_position_compatible("WR", "DB") is False


def test_no_speculative_fb_to_rb_compatibility():
    """No real observed case has required this -- only exact equality
    is implemented (see module docstring)."""
    assert is_position_compatible("RB", "FB") is False


def test_missing_candidate_position_is_not_compatible():
    assert is_position_compatible("QB", None) is False
    assert is_position_compatible("QB", "") is False


def test_flex_is_never_a_valid_base_position_input():
    with pytest.raises(ValueError):
        is_position_compatible("FLEX", "RB")


def test_dst_is_never_checked_through_this_module():
    with pytest.raises(ValueError):
        is_position_compatible("DST", "DST")
