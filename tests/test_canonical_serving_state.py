"""M1M -- serving-state foundation tests."""

import pytest

from canonical.serving_state import ABSENT, ALL_SERVING_STATES, FRESH, STALE, describe


def test_three_states_defined():
    assert ALL_SERVING_STATES == {FRESH, STALE, ABSENT}


def test_absent_is_documented_as_a_valid_state_not_an_error():
    text = describe(ABSENT).lower()
    assert "error" not in text
    # explicitly disclaims the forbidden fallbacks, rather than being
    # silent about them
    assert "never" in text
    for disclaimed in ("mock", "synthetic", "fabricat"):
        assert disclaimed in text


def test_describe_unknown_state_raises():
    with pytest.raises(ValueError):
        describe("NOT_A_STATE")
