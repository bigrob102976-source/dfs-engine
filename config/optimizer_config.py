"""Centralized configuration for the DraftKings MLB lineup optimizer
(Milestone 9). Every tunable the solver/generator needs lives here so
none of it is scattered through optimizer/*.py.
"""

OPTIMIZER_VERSION = "0.1.0"

# "balanced" objective mode: weighted blend of projection and ceiling.
# Must sum to 1.0 -- enforced by a test, not at import time (keeps this
# file plain data, matching config/scoring_config.py's style).
BALANCED_OBJECTIVE_WEIGHTS = {
    "projection": 0.70,
    "ceiling": 0.30,
}

OBJECTIVE_MODES = ("projection", "ceiling", "balanced", "leverage")

# "leverage" objective mode (Milestone 10): same projection/ceiling blend
# as "balanced", plus a small additive leverage nudge. The nudge is
# capped in DK-point terms (not percentile terms) so it can never
# dominate quality -- a terrible, low-owned play cannot become "optimal"
# just because nobody else owns it. leverage_score is expected to range
# roughly [-100, 100] (a percentile difference); dividing by 100 and
# multiplying by the cap turns it into a modest point-equivalent nudge.
LEVERAGE_OBJECTIVE_PROJECTION_WEIGHT = 0.70
LEVERAGE_OBJECTIVE_CEILING_WEIGHT = 0.30
LEVERAGE_OBJECTIVE_BONUS_MAX_POINTS = 3.0

DEFAULT_MIN_UNIQUE = 1
DEFAULT_MAX_EXPOSURE = 1.0  # V1: unrestricted unless the user supplies a cap

# DraftKings does not publish a machine-readable "no pitcher vs. the
# hitters he's facing" rule, but it's the standard GPP-construction
# default nearly every DFS player and tool applies (a strikeout by your
# own pitcher directly zeroes out an opposing hitter's plate appearance).
# Kept as a named, overridable default rather than hardcoded in the
# solver, per the milestone's explicit "configurable constraint" instruction.
ALLOW_PITCHER_VS_HITTER_DEFAULT = False

# CP-SAT determinism: single worker + fixed seed so identical inputs
# always produce identical output ordering (no wall-clock/thread-count
# dependent search behavior).
SOLVER_NUM_SEARCH_WORKERS = 1
SOLVER_RANDOM_SEED = 42
SOLVER_MAX_TIME_SECONDS = 30.0

# Milestone 14: the batch CLI's 30s-per-solve cap is fine for an
# unattended pipeline run but far too slow for a human clicking BUILD in
# the dashboard and waiting -- a 20-lineup request could take up to 10
# minutes worst case. The interactive dashboard build endpoint passes
# this (via OptimizerSettings.time_limit_seconds) instead, trading a
# smaller CP-SAT search budget per lineup for a responsive UI. This does
# NOT change the math itself (same model, same constraints, same
# determinism) -- only how long the solver is allowed to look before
# returning its best answer so far.
INTERACTIVE_SOLVER_MAX_TIME_SECONDS = 8.0
