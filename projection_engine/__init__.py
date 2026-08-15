"""AI Projection Engine (Milestone 20): the final projection layer the
optimizer can select alongside Independent / External / Adjusted.

This package never recomputes a Pitcher Agent, Batter Agent, Game
Environment Agent, or Ownership model calculation -- it only reads their
already-persisted snapshot outputs and combines them, with reasons, into
one AI Projection per player. See config/projection_engine_config.py for
every weight and threshold used.
"""
