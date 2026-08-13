"""Per-player objective value for each supported objective mode.
Deliberately simple and deterministic. The "leverage" mode (Milestone
10) still keeps projection/ceiling as the dominant signal -- leverage
only ever contributes a small, capped point-equivalent nudge (see
LEVERAGE_OBJECTIVE_BONUS_MAX_POINTS) so a low-owned but weak play can
never become "optimal" purely because it's unpopular.
"""

from config.optimizer_config import (
    BALANCED_OBJECTIVE_WEIGHTS,
    LEVERAGE_OBJECTIVE_BONUS_MAX_POINTS,
    LEVERAGE_OBJECTIVE_CEILING_WEIGHT,
    LEVERAGE_OBJECTIVE_PROJECTION_WEIGHT,
    OBJECTIVE_MODES,
)
from optimizer.models import OptimizerPlayer


class InvalidObjectiveModeError(ValueError):
    pass


def player_objective_value(player: OptimizerPlayer, mode: str) -> float:
    if mode == "projection":
        return player.projection
    if mode == "ceiling":
        return player.ceiling
    if mode == "balanced":
        return (
            BALANCED_OBJECTIVE_WEIGHTS["projection"] * player.projection
            + BALANCED_OBJECTIVE_WEIGHTS["ceiling"] * player.ceiling
        )
    if mode == "leverage":
        base = (
            LEVERAGE_OBJECTIVE_PROJECTION_WEIGHT * player.projection
            + LEVERAGE_OBJECTIVE_CEILING_WEIGHT * player.ceiling
        )
        leverage_component = 0.0
        if player.leverage_score is not None:
            leverage_component = (player.leverage_score / 100.0) * LEVERAGE_OBJECTIVE_BONUS_MAX_POINTS
        return base + leverage_component
    raise InvalidObjectiveModeError(f"Unknown objective mode {mode!r}; expected one of {OBJECTIVE_MODES}")


# CP-SAT works on integers -- objective values are scaled up and rounded
# so fractional projection points aren't lost, then the solver's raw sum
# is scaled back down for reporting.
OBJECTIVE_SCALE = 1000


def scaled_objective_value(player: OptimizerPlayer, mode: str) -> int:
    return round(player_objective_value(player, mode) * OBJECTIVE_SCALE)
