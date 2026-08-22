"""Milestone 32.2B -- Big Money ML: live SHADOW inference for the
approved historical_models.pitcher_v1 (M32.2) pitcher model.

This package is a live evaluation competitor, not a production
projection source. It:

  - loads the FROZEN M32.2 model artifact (never retrains, never tunes)
  - builds today's pregame features using the SAME feature-computation
    functions training used (historical_mlb.rolling /
    historical_mlb.statcast_aggregation / historical_mlb.pitcher_features'
    private helper), fed by freshly live-fetched data instead of the
    historical warehouse -- never a second, independently-defined
    feature calculation system
  - persists projections to a sibling ml_projection_snapshots/ directory
  - is never imported by native_projections/, projection_engine/,
    ownership/, or optimizer/ (see tests/test_architecture_separation.py)
  - is never consumed by the optimizer's ProjectionSource

See CLAUDE.md and the M32.2B milestone spec for the full list of
guarantees this package must uphold.
"""

BIG_MONEY_ML_SOURCE_KEY = "big_money_ml"
BIG_MONEY_ML_LABEL = "Big Money ML"
