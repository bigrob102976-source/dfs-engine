"""MLB DFS projected-ownership model (Milestone 10).

Estimates projected_ownership (a MODEL PREDICTION, never presented as
actual/field ownership -- see CLAUDE.md's "never invent statistics" and
this milestone's naming rule) from pregame information already present
on a saved DK player pool: salary, position, projection, ceiling,
batting order, and team context. Never reads evaluation/ (postgame
results) or agents/ (it does not re-score players, only reads their
already-computed projections) -- see tests/test_architecture_separation.py.
"""
