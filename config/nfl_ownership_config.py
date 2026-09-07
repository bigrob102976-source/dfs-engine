"""Centralized configuration for NFL M12's Big Money Native NFL ownership
estimator (nfl_ownership_v1).

Sibling to config/ownership_config.py (MLB) -- kept as its own file
rather than extending that module, since NFL's roster shape (a shared
FLEX slot spanning RB/WR/TE) has no MLB analog and the weight/threshold
VALUES below are NFL-native starting points, not ported MLB numbers
(see NFL M12's Phase 0 audit: MLB's thresholds were hand-tuned for
MLB's slate shape and roster size, and must not be reused as-is).

This is a DETERMINISTIC, hand-set estimator -- explicitly NOT fit or
tuned from any slate's outcomes (mirrors config/ownership_config.py's
own "Do NOT optimize ownership model weights from one slate" rule).
No real historical DraftKings NFL ownership data exists in this repo
(NFL M12 Phase 4 audit), so there is nothing to fit against even if
that were desired -- this file's numbers are a transparent, documented
starting point, meant to be revisited once real historical ownership
becomes available (see nfl/ownership_model.py's module docstring).
"""

NFL_OWNERSHIP_MODEL_VERSION = "nfl_ownership_v1"
NFL_OWNERSHIP_METHOD = "deterministic_estimator"
NFL_OWNERSHIP_SOURCE = "BIG_MONEY_NATIVE_OWNERSHIP_V1"

# ----------------------------------------------------------------------------
# Raw popularity score: weighted blend of 0-100-scaled features, per
# position. Each dict must sum to 1.0 (enforced by a test).
# ----------------------------------------------------------------------------

QB_OWNERSHIP_WEIGHTS = {
    "projection_percentile": 0.35,
    "value_percentile": 0.20,
    "salary_percentile": 0.15,
    "ceiling_percentile": 0.15,
    "team_total_percentile": 0.15,  # neutral 50.0 whenever Vegas isn't configured
}

# RB/WR/TE share one weight shape (usage_percentile means a different
# underlying stat per position -- carry+target share for RB, target+
# reception share for WR/TE -- see nfl/ownership_features.py) but each
# position gets its OWN copy so a future position-specific retune never
# accidentally moves another position's weights.
_FLEX_POSITION_WEIGHTS = {
    "projection_percentile": 0.30,
    "value_percentile": 0.20,
    "usage_percentile": 0.20,
    "ceiling_percentile": 0.15,
    "salary_percentile": 0.15,
}
RB_OWNERSHIP_WEIGHTS = dict(_FLEX_POSITION_WEIGHTS)
WR_OWNERSHIP_WEIGHTS = dict(_FLEX_POSITION_WEIGHTS)
TE_OWNERSHIP_WEIGHTS = dict(_FLEX_POSITION_WEIGHTS)

DST_OWNERSHIP_WEIGHTS = {
    "salary_percentile": 0.30,
    "projection_percentile": 0.30,
    # Low opponent implied total / high opponent weakness -> more
    # popular DST. Neutral 50.0 whenever Vegas isn't configured (never
    # blocks DST ownership -- see nfl/ownership_features.py).
    "opponent_weakness_percentile": 0.40,
}

POSITION_OWNERSHIP_WEIGHTS = {
    "QB": QB_OWNERSHIP_WEIGHTS,
    "RB": RB_OWNERSHIP_WEIGHTS,
    "WR": WR_OWNERSHIP_WEIGHTS,
    "TE": TE_OWNERSHIP_WEIGHTS,
    "DST": DST_OWNERSHIP_WEIGHTS,
}

# ----------------------------------------------------------------------------
# FLEX normalization (NFL M12 Phase 7 -- the one problem MLB's ownership
# model never had to solve, since MLB Classic has no shared-eligibility
# slot). See nfl/ownership_model.py::_allocate_flex_ownership() for the
# full algorithm this feeds.
#
# RB/WR/TE each first get their OWN guaranteed-slot ownership mass
# (RB: 2*100=200, WR: 3*100=300, TE: 1*100=100 -- their DK roster slot
# counts). The single shared FLEX slot's 100% of ownership mass is then
# allocated across the combined RB+WR+TE pool using each player's
# percentile rank WITHIN that combined pool (not their own-position
# percentile -- FLEX competition is cross-position), raised to this
# exponent before proportional redistribution. An exponent of 1.0 would
# spread FLEX ownership flatly in proportion to raw combined-percentile,
# handing meaningful FLEX share to replacement-level players who
# realistically draw ~0% FLEX ownership in real DK contests; raising the
# score concentrates the shared pool toward the players who actually
# compete for FLEX (stars and clear values), while remaining a smooth,
# continuous function of quality (no hard bench/starter cutoff, which
# would be a much more arbitrary, harder-to-justify design). This
# exponent is a deliberate, documented modeling choice -- not fit from
# any slate's outcome data (no such data exists yet, see this module's
# top docstring) -- and should be revisited once real historical NFL
# DK FLEX ownership is available to check against.
# ----------------------------------------------------------------------------

FLEX_CONCENTRATION_EXPONENT = 2.0

# Same concentration rationale as FLEX_CONCENTRATION_EXPONENT immediately
# above, applied to each position's OWN base (guaranteed-slot) raw
# score before normalize_with_cap redistributes that position's slot
# mass. Without this, a percentile-blended raw score is nearly LINEAR
# in rank (percentiles spread roughly evenly across a pool regardless
# of the true skill gap between the best and 50th-best player), so
# normalize_with_cap's proportional split hands almost every player in
# a large position pool a near-identical, near-zero share -- observed
# directly on the real DraftGroup 151307 slate (NFL M12 Phase 11 sanity
# check): the top QB by every real signal (best projection, best value)
# came out at only ~2% projected ownership across an 89-QB pool, which
# is not a plausible real-world DK ownership shape (a clear best play
# at a scarce, one-slot position like QB regularly clears 15-30%+ real
# ownership). Squaring the raw score before normalization concentrates
# mass toward the players who are ACTUALLY the best plays -- a smooth,
# continuous, still fully rank-preserving transform, not a hard cutoff.
BASE_CONCENTRATION_EXPONENT = 2.0

# ----------------------------------------------------------------------------
# Ownership tiers -- deterministic buckets, (name, low_inclusive, high_exclusive).
# NFL Classic pools are typically smaller than MLB's multi-slate-day
# pools and every roster includes exactly one guaranteed-100%-mass QB
# and DST slot, so chalk concentrates faster than MLB -- these edges are
# intentionally lower than config/ownership_config.py's MLB thresholds.
# ----------------------------------------------------------------------------

OWNERSHIP_TIER_THRESHOLDS = [
    ("very_low", 0.0, 3.0),
    ("low", 3.0, 8.0),
    ("medium", 8.0, 18.0),
    ("high", 18.0, 30.0),
    ("very_high", 30.0, 100.0001),
]

CHALK_OWNERSHIP_THRESHOLD = 18.0

# ----------------------------------------------------------------------------
# Leverage tags -- same shape/semantics as config/ownership_config.py's
# LEVERAGE_TAG_THRESHOLDS, own NFL-native numbers.
# ----------------------------------------------------------------------------

LEVERAGE_TAG_THRESHOLDS = {
    "elite_leverage": 30.0,
    "positive_leverage": 12.0,
    "negative_leverage": -12.0,
    "low_owned_ceiling_max_ownership": 6.0,
    "low_owned_ceiling_min_ceiling_percentile": 80.0,
    "contrarian_max_ownership": 4.0,
    "contrarian_min_quality_percentile": 60.0,
    "chalk_min_ownership_tier": "high",  # "high" or "very_high" -> chalk tag
}

# ----------------------------------------------------------------------------
# Ownership confidence -- deliberately separate from projection confidence.
# ----------------------------------------------------------------------------

OWNERSHIP_CONFIDENCE_WEIGHTS = {
    "slate_size_factor": 0.30,
    "position_pool_factor": 0.35,
    "input_completeness_factor": 0.35,
}
MIN_COMPARABLE_PLAYERS_FOR_FULL_CONFIDENCE = 4
# A real DK Classic NFL slate (main slate) commonly has 400-700+
# rosterable players; this is the pool size at/above which slate-size
# confidence saturates at 1.0 -- a smaller (e.g. Thursday/Sunday-night
# single-game-adjacent Classic, or an early-week short slate) pool
# scales down proportionally, never treated as equally confident.
SLATE_SIZE_FULL_CONFIDENCE_PLAYER_COUNT = 200

VALUE_NORMALIZATION_CONSTANT = 10000

# Allowed floating-point/redistribution slack when checking that each
# position pool's ownership mass sums to its expected roster-implied total.
OWNERSHIP_NORMALIZATION_TOLERANCE = 1.0
