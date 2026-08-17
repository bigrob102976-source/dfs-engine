"""One identifier for "which version of the Native Projection Model produced
this snapshot." Bump by hand whenever the methodology in hitter_rates.py /
pitcher_rates.py / matchup.py / uncertainty.py / config/native_projection_config.py
changes in a way that would make old native projections not directly
comparable to new ones -- same convention as
config.scoring_config.PITCHER_MODEL_VERSION and
config.batter_scoring_config.BATTER_MODEL_VERSION. Every saved snapshot
(native_projections/persistence.py) records this."""

NATIVE_PROJECTION_MODEL_VERSION = "1.0.0"
