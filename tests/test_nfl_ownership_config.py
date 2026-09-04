"""NFL M12 -- config/nfl_ownership_config.py's weight dicts must each
sum to 1.0, exactly like config/ownership_config.py's own MLB weights
are required to (mirrors that module's enforced invariant)."""

import pytest

from config.nfl_ownership_config import POSITION_OWNERSHIP_WEIGHTS


@pytest.mark.parametrize("position", sorted(POSITION_OWNERSHIP_WEIGHTS))
def test_position_weights_sum_to_one(position):
    weights = POSITION_OWNERSHIP_WEIGHTS[position]
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)
