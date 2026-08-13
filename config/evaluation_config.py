"""Configuration for the pregame-vs-actual evaluation system (Milestone 6).

Deliberately kept SEPARATE from config/scoring_config.py: this file
controls how we MEASURE the Pitcher Agent after the fact. Nothing here
feeds into agents/pitcher_agent.py, and nothing in scoring_config.py
should be tuned from numbers computed using this file -- that is a
future milestone's job, only after many slates of evidence. This
milestone is measurement infrastructure, not tuning.
"""

# Risk-score buckets (risk_score is 0-100; see config.scoring_config.RISK_MODEL).
RISK_BUCKETS = [
    {"label": "low", "low": 0.0, "high": 35.0},
    {"label": "medium", "low": 35.0, "high": 50.0},
    {"label": "high", "low": 50.0, "high": 100.01},  # .01 so a risk of exactly 100 still falls in "high"
]

# Confidence-score buckets, exactly as specified for this milestone.
CONFIDENCE_BUCKETS = [
    {"label": "0-39", "low": 0.0, "high": 40.0},
    {"label": "40-49", "low": 40.0, "high": 50.0},
    {"label": "50-59", "low": 50.0, "high": 60.0},
    {"label": "60-69", "low": 60.0, "high": 70.0},
    {"label": "70-79", "low": 70.0, "high": 80.0},
    {"label": "80+", "low": 80.0, "high": 100.01},
]

TOP_N_HIT_RATES = [5, 10]
BEST_WORST_CALL_COUNT = 5
SURPRISE_BUST_COUNT = 5

# Statuses (see evaluation/results_enrichment.py) that count toward standard
# projection-accuracy metrics (MAE/RMSE/correlation/rank/hit-rate/etc).
# Anything else (scratched, postponed, did_not_start, game_incomplete,
# missing_result) is reported separately, never silently folded in or
# silently dropped.
ACCURACY_ELIGIBLE_STATUSES = {"completed_start"}
