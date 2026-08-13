"""Configuration for evaluating Ownership Model V1 against actual
DraftKings contest ownership (Milestone 11).

Deliberately separate from config/ownership_config.py, the same way
config/evaluation_config.py is kept separate from config/scoring_config.py:
this file controls how we MEASURE the ownership model after a contest
locks. Nothing here feeds back into ownership/*.py, and no ownership
model weight/threshold should be tuned from numbers computed using this
file -- that is a future milestone's job, only after many contests of
evidence. This milestone is measurement infrastructure, not tuning.
"""

OWNERSHIP_EVALUATOR_VERSION = "0.1.0"

# ----------------------------------------------------------------------------
# Chalk evaluation. "threshold" compares each player's ownership (projected
# and actual, independently) against CHALK_EVAL_OWNERSHIP_THRESHOLD;
# "top_n" instead takes the top CHALK_EVAL_TOP_N by projected/actual
# ownership as each side's "chalk set". Kept configurable and separate
# from config.ownership_config.CHALK_OWNERSHIP_THRESHOLD (that one
# labels a single player's lineup-metric contribution; this one defines
# the evaluator's own chalk-set membership rule).
# ----------------------------------------------------------------------------

CHALK_EVAL_MODE = "threshold"  # "threshold" | "top_n"
CHALK_EVAL_OWNERSHIP_THRESHOLD = 20.0
CHALK_EVAL_TOP_N = 5

TOP_N_HIT_RATES = [5, 10]
BIGGEST_MISSES_COUNT = 10
TOP_ACTUAL_OWNERSHIP_DISPLAY_COUNT = 10

# Leverage/ownership tags (assigned pregame by ownership/leverage.py) worth
# evaluating individually -- does actual ownership behave the way the tag implied?
TAGS_TO_EVALUATE = ["positive_leverage", "elite_leverage", "negative_leverage", "chalk", "low_owned_ceiling", "contrarian"]

# (low_inclusive, high_exclusive, label) -- exact bands configurable, per the milestone.
PITCHER_SALARY_BANDS = [
    (0, 7000, "<$7K"),
    (7000, 8000, "$7K-$8K"),
    (8000, 9000, "$8K-$9K"),
    (9000, 10_000_000, "$9K+"),
]
HITTER_SALARY_BANDS = [
    (0, 3000, "<$3K"),
    (3000, 4000, "$3K-$4K"),
    (4000, 5000, "$4K-$5K"),
    (5000, 10_000_000, "$5K+"),
]
