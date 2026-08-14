"""Single source of truth for the Big Money Research Adjustment Layer
(Milestone 17): how far the adjustment engine is allowed to move an
external provider's baseline projection, and which structured-research
signals it reacts to.

The adjustment engine is NOT an LLM free-form projection generator --
it is a deterministic function of already-computed Pitcher/Batter Agent
snapshot fields (trend_metrics, opposing_pitcher/opponent_stats,
confidence). See external_projections/adjustment_engine.py.
"""

# --- Model version -----------------------------------------------------------

BIG_MONEY_ADJUSTMENT_VERSION = "0.1.0"

# --- Safety caps ---------------------------------------------------------
# No signal combination may ever move a projection further than this,
# regardless of how many favorable/unfavorable signals fire.

MAX_POSITIVE_ADJUSTMENT_PERCENT = 15.0
MAX_NEGATIVE_ADJUSTMENT_PERCENT = 15.0

# Confidence (0-100, the SAME `confidence` field already on every
# pitcher/batter board record) further restricts the cap -- low-sample
# research must not be allowed to move a projection as far as
# high-confidence research, even before the absolute caps above are
# considered. Bands are checked low-to-high; the first match wins.
CONFIDENCE_ADJUSTMENT_CAPS = [
    {"min_confidence": 70.0, "max_percent": 15.0},
    {"min_confidence": 40.0, "max_percent": 10.0},
    {"min_confidence": 0.0, "max_percent": 5.0},
]
# Used when a player's research record has no `confidence` value at all
# (should be rare) -- the most conservative band, never the most permissive.
DEFAULT_CONFIDENCE_ADJUSTMENT_CAP_PERCENT = 5.0

# --- Signal thresholds -----------------------------------------------------
# Each signal reads one already-computed field from the latest batter_board
# / pitcher_board snapshot record (trend_metrics.*, opposing_pitcher.* /
# opponent_stats.*). `positive_delta`/`negative_delta` are raw fantasy-point
# adjustments (matching the milestone's own worked example: "+0.4 positive
# hard-hit trend"), applied when the field's value crosses the given
# threshold in the favorable/unfavorable direction. A signal that is
# missing (None) simply does not fire -- it is never treated as zero or
# neutral, since a missing stat is not the same claim as an unchanged one.

BATTER_SIGNALS = [
    {
        "factor": "recent_hard_hit_trend",
        "path": ("trend_metrics", "hard_hit_trend"),
        "positive_threshold": 2.0,
        "positive_delta": 0.4,
        "positive_reason": "positive recent hard-hit trend",
        "negative_threshold": -2.0,
        "negative_delta": -0.3,
        "negative_reason": "declining recent hard-hit rate",
    },
    {
        "factor": "recent_xwoba_trend",
        "path": ("trend_metrics", "xwoba_trend"),
        "positive_threshold": 0.015,
        "positive_delta": 0.3,
        "positive_reason": "recent xwOBA trending up",
        "negative_threshold": -0.015,
        "negative_delta": -0.3,
        "negative_reason": "recent xwOBA trending down",
    },
    {
        "factor": "recent_barrel_trend",
        "path": ("trend_metrics", "barrel_trend"),
        "positive_threshold": 1.5,
        "positive_delta": 0.2,
        "positive_reason": "barrel rate trending up",
        "negative_threshold": -1.5,
        "negative_delta": -0.2,
        "negative_reason": "barrel rate trending down",
    },
    {
        "factor": "recent_strikeout_rate_trend",
        "path": ("trend_metrics", "strikeout_rate_trend"),
        "positive_threshold": 2.0,
        "positive_delta": 0.2,
        "positive_reason": "recent strikeout rate improving",
        "negative_threshold": -2.0,
        "negative_delta": -0.2,
        "negative_reason": "elevated recent strikeout risk",
    },
    {
        "factor": "opposing_pitcher_quality",
        "path": ("opposing_pitcher", "xwoba_allowed"),
        "positive_threshold": 0.320,
        "positive_delta": 0.3,
        "positive_reason": "favorable opposing pitcher",
        "negative_threshold": 0.290,
        "negative_delta": -0.2,
        "negative_reason": "difficult opposing pitcher matchup",
    },
]

PITCHER_SIGNALS = [
    {
        "factor": "velocity_trend",
        "path": ("trend_metrics", "velocity_trend"),
        "positive_threshold": 0.5,
        "positive_delta": 0.3,
        "positive_reason": "velocity trending up",
        "negative_threshold": -0.5,
        "negative_delta": -0.3,
        "negative_reason": "velocity trending down",
    },
    {
        "factor": "csw_trend",
        "path": ("trend_metrics", "csw_trend"),
        "positive_threshold": 1.5,
        "positive_delta": 0.3,
        "positive_reason": "CSW% trending up",
        "negative_threshold": -1.5,
        "negative_delta": -0.3,
        "negative_reason": "CSW% trending down",
    },
    {
        "factor": "swinging_strike_trend",
        "path": ("trend_metrics", "swinging_strike_trend"),
        "positive_threshold": 1.0,
        "positive_delta": 0.2,
        "positive_reason": "swinging-strike rate trending up",
        "negative_threshold": -1.0,
        "negative_delta": -0.2,
        "negative_reason": "swinging-strike rate trending down",
    },
    {
        # TrendMetrics.hard_hit_trend is already inverted at the source
        # (season - recent), so positive here already means "hard-hit
        # rate ALLOWED went down" -- no `invert` needed.
        "factor": "hard_hit_allowed_trend",
        "path": ("trend_metrics", "hard_hit_trend"),
        "positive_threshold": 2.0,
        "positive_delta": 0.3,
        "positive_reason": "opponent hard-hit rate allowed trending down",
        "negative_threshold": -2.0,
        "negative_delta": -0.2,
        "negative_reason": "opponent hard-hit rate allowed trending up",
    },
    {
        "factor": "opponent_matchup",
        "path": ("opponent_stats", "strikeout_percent"),
        "positive_threshold": 24.0,
        "positive_delta": 0.3,
        "positive_reason": "favorable strikeout matchup",
        "negative_threshold": 18.0,
        "negative_delta": -0.2,
        "negative_reason": "difficult contact-oriented opponent",
    },
]
