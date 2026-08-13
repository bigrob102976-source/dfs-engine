import pytest

from config.optimizer_config import BALANCED_OBJECTIVE_WEIGHTS
from optimizer.objective import InvalidObjectiveModeError, player_objective_value, scaled_objective_value
from tests._optimizer_fixtures import hitter


def test_projection_mode():
    p = hitter("h1", "AAA", ["OF"], 3000, 10.0, ceiling=18.0)
    assert player_objective_value(p, "projection") == 10.0


def test_ceiling_mode():
    p = hitter("h1", "AAA", ["OF"], 3000, 10.0, ceiling=18.0)
    assert player_objective_value(p, "ceiling") == 18.0


def test_balanced_mode_uses_centralized_weights():
    p = hitter("h1", "AAA", ["OF"], 3000, 10.0, ceiling=18.0)
    expected = BALANCED_OBJECTIVE_WEIGHTS["projection"] * 10.0 + BALANCED_OBJECTIVE_WEIGHTS["ceiling"] * 18.0
    assert player_objective_value(p, "balanced") == pytest.approx(expected)


def test_balanced_weights_sum_to_one():
    assert sum(BALANCED_OBJECTIVE_WEIGHTS.values()) == pytest.approx(1.0)


def test_invalid_mode_raises():
    p = hitter("h1", "AAA", ["OF"], 3000, 10.0)
    with pytest.raises(InvalidObjectiveModeError):
        player_objective_value(p, "ownership")


def test_scaled_objective_value_is_integer():
    p = hitter("h1", "AAA", ["OF"], 3000, 10.25)
    assert scaled_objective_value(p, "projection") == 10250
