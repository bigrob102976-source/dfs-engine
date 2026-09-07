"""NFL M13 -- centralized configuration for the NFL solver's tournament
lineup-construction controls (stacking, leverage objective, exposure).

Sibling to config/optimizer_config.py (MLB) -- kept as its own file so
MLB's config stays byte-for-byte unchanged. Values here are NFL-native
starting points documented the same way config/nfl_ownership_config.py's
were in NFL M12: transparent, hand-set, never fit from a slate's outcome
data (no such data exists for this project to fit against).
"""

NFL_OPTIMIZER_VERSION = "0.1.0"

# "leverage" objective mode -- same shape as MLB's LEVERAGE_OBJECTIVE_*
# constants (config/optimizer_config.py), same rationale: leverage only
# ever contributes a small, CAPPED point-equivalent nudge on top of a
# projection/ceiling blend, so a low-owned but weak play can never
# become "optimal" purely because it's unpopular. leverage_score comes
# from nfl/ownership_model.py (NFL M12), expected to range roughly
# [-100, 100] (a percentile difference) -- dividing by 100 and
# multiplying by the cap turns it into a modest point-equivalent nudge,
# identical in spirit to MLB's own audited implementation
# (optimizer/objective.py).
NFL_LEVERAGE_PROJECTION_WEIGHT = 0.70
NFL_LEVERAGE_CEILING_WEIGHT = 0.30
NFL_LEVERAGE_BONUS_MAX_POINTS = 3.0

# Player-scoring objective modes (in addition to "roster_feasibility",
# which maximizes salary utilization and needs no player-level scoring
# data at all -- see nfl/solver.py). Each of these three modes requires
# a player to have a real projection; "ceiling" and "leverage" ALSO
# require a real ceiling (never substituted/fabricated from projection
# -- a player missing ceiling is simply not a candidate in those two
# modes, mirroring "projection" mode's existing "no projection -> not a
# candidate" rule from NFL M4).
NFL_SCORING_OBJECTIVE_MODES = ("projection", "ceiling", "leverage")
NFL_ALL_OBJECTIVE_MODES = ("roster_feasibility",) + NFL_SCORING_OBJECTIVE_MODES

DEFAULT_MAX_EXPOSURE = 1.0  # unrestricted unless the user supplies a cap
DEFAULT_MIN_EXPOSURE = 0.0

# NFL M13 stacking. Pass-catcher positions eligible to satisfy a QB
# stack or bring-back requirement -- RB and DST are deliberately
# excluded (a check-down RB isn't the "correlation" a QB stack
# represents, and DST can never satisfy either rule -- NFL M13 Phase 2/3's
# own explicit instruction).
QB_STACK_PASS_CATCHER_POSITIONS = frozenset({"WR", "TE"})
BRING_BACK_ELIGIBLE_POSITIONS = frozenset({"RB", "WR", "TE"})

QB_STACK_MODES = ("off", "single", "double")
BRING_BACK_MODES = ("off", "one")
QB_STACK_RECEIVER_COUNTS = {"off": 0, "single": 1, "double": 2}
BRING_BACK_COUNTS = {"off": 0, "one": 1}
