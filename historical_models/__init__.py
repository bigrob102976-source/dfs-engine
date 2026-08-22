"""Milestone 32.2 -- historical, warehouse-trained DFS projection models.

Deliberately separate from the LIVE pipeline (native_projections/,
projection_engine/, agents/) -- nothing here is wired into the
optimizer or the dashboard. This is evaluation-first research: does a
model trained on historical_mlb's warehouse beat simple baselines at
predicting actual DraftKings points? Shadow-mode wiring (reading
today's live pregame features through this model for comparison only,
never feeding the optimizer) is a future milestone's decision, gated on
this one's own GO/NO-GO verdict.
"""
