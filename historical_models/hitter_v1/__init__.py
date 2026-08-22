"""Milestone 32.3 -- Big Money DFS Historical Hitter Model V1.

Sibling package to historical_models.pitcher_v1 (Milestone 32.2), same
evaluation-first discipline: trains against the M32.1 historical
warehouse, never touches the live pipeline, never wired into the
optimizer/agents. Nothing in this package is imported by pitcher_v1,
and pitcher_v1 is never imported by this package -- see
tests/test_architecture_separation.py for the isolation guard.
"""

BIG_MONEY_HITTER_MODEL_VERSION = "1.0.0"
