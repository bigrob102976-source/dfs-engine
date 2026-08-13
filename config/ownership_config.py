"""Centralized configuration for the MLB DFS ownership model (Milestone
10). Every weight/threshold the ownership feature builder, model, and
leverage logic use lives here so none of it is scattered through
ownership/*.py.

These weights are a transparent, hand-set starting point (explicitly
NOT fit/tuned from any slate's data -- see CLAUDE.md and the milestone's
"Do NOT optimize ownership model weights from one slate" instruction).
"""

OWNERSHIP_MODEL_VERSION = "0.1.0"

# ----------------------------------------------------------------------------
# Raw popularity score: weighted blend of 0-100-scaled features, per
# player type. Each dict must sum to 1.0 (enforced by a test).
# ----------------------------------------------------------------------------

PITCHER_OWNERSHIP_WEIGHTS = {
    "projection_percentile": 0.25,
    "value_percentile": 0.20,
    "salary_savings_percentile": 0.15,
    "overall_score_percentile": 0.15,
    "k_upside": 0.10,
    "confidence": 0.05,
    "opponent_weakness_percentile": 0.10,
}

HITTER_OWNERSHIP_WEIGHTS = {
    "projection_percentile": 0.25,
    "value_percentile": 0.20,
    "overall_score_percentile": 0.15,
    "position_scarcity": 0.10,
    "team_popularity": 0.10,
    "batting_order_effect": 0.10,
    "power_signal": 0.05,
    "confidence": 0.05,
}

# ----------------------------------------------------------------------------
# Chalk score: a separate 0-100 "how likely to be popular" score, not the
# same number as projected_ownership itself.
# ----------------------------------------------------------------------------

CHALK_SCORE_WEIGHTS = {
    "ownership_percentile": 0.40,
    "projection_percentile": 0.25,
    "value_percentile": 0.15,
    "secondary_percentile": 0.10,  # position_scarcity (hitters) / salary_savings_percentile (pitchers)
    "team_popularity": 0.10,       # neutral 50.0 for pitchers (no team-popularity concept)
}

# ----------------------------------------------------------------------------
# Ownership tiers -- deterministic buckets, (name, low_inclusive, high_exclusive).
# ----------------------------------------------------------------------------

OWNERSHIP_TIER_THRESHOLDS = [
    ("very_low", 0.0, 5.0),
    ("low", 5.0, 10.0),
    ("medium", 10.0, 20.0),
    ("high", 20.0, 30.0),
    ("very_high", 30.0, 100.0001),
]

# The ownership level (%) at which a player counts toward a lineup's
# "players_above_chalk_threshold" metric -- aligned with the "high" tier's
# lower bound above so "chalk" means the same thing everywhere.
CHALK_OWNERSHIP_THRESHOLD = 20.0

# ----------------------------------------------------------------------------
# Leverage tags.
# ----------------------------------------------------------------------------

LEVERAGE_TAG_THRESHOLDS = {
    "elite_leverage": 30.0,
    "positive_leverage": 12.0,
    "negative_leverage": -12.0,
    "low_owned_ceiling_max_ownership": 7.0,
    "low_owned_ceiling_min_ceiling_percentile": 80.0,
    "contrarian_max_ownership": 5.0,
    "contrarian_min_quality_percentile": 60.0,
    "chalk_min_ownership_tier": "high",  # "high" or "very_high" -> chalk tag
    "value_chalk_min_value_percentile": 70.0,
    "expensive_chalk_min_salary_percentile": 75.0,
}

# ----------------------------------------------------------------------------
# Small-sample dampening (hitters only -- see CLAUDE.md's Milestone 7/9
# small-sample-hitter finding). Mirrors the linear-penalty shape already
# used throughout config/scoring_config.py and config/batter_scoring_config.py,
# duplicated here (not imported) to keep ownership/ decoupled from agents/.
# ----------------------------------------------------------------------------

SAMPLE_SIZE_DAMPENING = {
    "season_pa_threshold": 150,   # at/above this PA, full weight (1.0)
    "season_pa_floor": 20,        # at/below this PA, the minimum dampening factor applies
    "min_dampening_factor": 0.40,
}

# ----------------------------------------------------------------------------
# Batting order effect (hitters). Unknown order falls back to the default.
# ----------------------------------------------------------------------------

BATTING_ORDER_OWNERSHIP_WEIGHT = {
    1: 100.0, 2: 95.0, 3: 90.0, 4: 85.0, 5: 70.0, 6: 55.0, 7: 40.0, 8: 30.0, 9: 20.0,
}
DEFAULT_BATTING_ORDER_WEIGHT = 50.0

# ----------------------------------------------------------------------------
# Position scarcity (hitters). An alternative at a position counts as
# "attractive" if its projection is within this fraction of the best
# projection at that position; scarcity saturates (bonus caps at 0) once
# this many attractive alternatives exist.
# ----------------------------------------------------------------------------

POSITION_SCARCITY_QUALITY_FRACTION = 0.70
POSITION_SCARCITY_SATURATION_COUNT = 6

# Purely a magnitude constant for the human-readable "value" feature
# (projection / salary * this). Ownership itself is driven by the
# slate-relative percentile of this value, never the raw number.
VALUE_NORMALIZATION_CONSTANT = 10000

# ----------------------------------------------------------------------------
# Ownership confidence -- deliberately separate from player quality/confidence.
# ----------------------------------------------------------------------------

OWNERSHIP_CONFIDENCE_WEIGHTS = {
    "slate_size_factor": 0.25,
    "lineup_completeness_factor": 0.35,
    "comparable_players_factor": 0.25,
    "input_completeness_factor": 0.15,
}
MIN_COMPARABLE_PLAYERS_FOR_FULL_CONFIDENCE = 4
SLATE_SIZE_FULL_CONFIDENCE_HITTER_COUNT = 60

# Allowed floating-point/redistribution slack when checking that the
# pitcher/hitter ownership pools sum to their expected totals.
OWNERSHIP_NORMALIZATION_TOLERANCE = 1.0
