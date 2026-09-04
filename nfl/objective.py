"""NFL M13 -- per-player objective value for each scoring objective mode
("projection", "ceiling", "leverage"; "roster_feasibility" needs no
player-level score at all and is handled directly in nfl/solver.py).

Mirrors optimizer/objective.py's exact leverage shape (audited in NFL
M13 Phase 8): projection/ceiling stay the DOMINANT signal, leverage only
ever contributes a small, capped point-equivalent nudge -- see
config/nfl_optimizer_config.py's docstring for the full rationale. NFL-
native weights, not MLB's constants (Phase 0's own instruction: do not
copy MLB constants blindly) -- values happen to match MLB's 0.70/0.30/
3.0 because that shape (dominant blend + small capped nudge) is sport-
agnostic and was independently a reasonable NFL starting point, not
because the MLB numbers were imported.
"""

from config.nfl_optimizer_config import (
    NFL_LEVERAGE_BONUS_MAX_POINTS,
    NFL_LEVERAGE_CEILING_WEIGHT,
    NFL_LEVERAGE_PROJECTION_WEIGHT,
    NFL_SCORING_OBJECTIVE_MODES,
)
from nfl.optimizer_models import NflOptimizerPlayer


class InvalidNflObjectiveModeError(ValueError):
    pass


def player_objective_value(player: NflOptimizerPlayer, mode: str) -> float:
    """Callers MUST have already filtered the candidate pool so every
    player passed here has the data this mode needs (see nfl/solver.py's
    per-mode candidate filtering) -- this function never substitutes a
    missing value, it assumes the caller already guaranteed real data."""
    if mode == "projection":
        return player.projection
    if mode == "ceiling":
        return player.ceiling
    if mode == "leverage":
        base = NFL_LEVERAGE_PROJECTION_WEIGHT * player.projection + NFL_LEVERAGE_CEILING_WEIGHT * player.ceiling
        # Missing leverage_score is handled explicitly, never fabricated
        # -- the player still participates in leverage mode using a
        # plain projection/ceiling blend (NFL M13 Phase 9's own
        # instruction: "handled explicitly", not excluded outright).
        # Mirrors optimizer/objective.py's identical, already-audited
        # MLB convention.
        leverage_component = 0.0
        if player.leverage_score is not None:
            leverage_component = (player.leverage_score / 100.0) * NFL_LEVERAGE_BONUS_MAX_POINTS
        return base + leverage_component
    raise InvalidNflObjectiveModeError(f"Unknown NFL scoring objective mode {mode!r}; expected one of {NFL_SCORING_OBJECTIVE_MODES}")


# CP-SAT works on integers -- objective values are scaled up and rounded
# so fractional projection points aren't lost. Mirrors optimizer/
# objective.py's OBJECTIVE_SCALE (and nfl/solver.py's pre-existing
# PROJECTION_OBJECTIVE_SCALE, which this supersedes for every scoring
# mode -- see nfl/solver.py).
OBJECTIVE_SCALE = 1000


def scaled_objective_value(player: NflOptimizerPlayer, mode: str) -> int:
    return round(player_objective_value(player, mode) * OBJECTIVE_SCALE)


def player_is_eligible_for_mode(player: NflOptimizerPlayer, mode: str) -> bool:
    """The exact "does this player have the real data this mode needs"
    rule -- never invents a projection/ceiling, so a player missing what
    a given mode requires is simply not a candidate (mirrors NFL M4's
    original "projection mode excludes unprojected players" rule,
    extended to ceiling/leverage). leverage_score is intentionally NOT
    checked here -- see player_objective_value()'s docstring for why a
    missing leverage_score doesn't exclude a player from leverage mode."""
    if mode == "roster_feasibility":
        return True
    if mode == "projection":
        return player.projection is not None
    if mode in ("ceiling", "leverage"):
        return player.projection is not None and player.ceiling is not None
    raise InvalidNflObjectiveModeError(f"Unknown NFL objective mode {mode!r}.")
