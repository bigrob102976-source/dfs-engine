"""DraftKings MLB Classic lineup optimizer (Milestone 9).

Deterministic mathematical optimization (OR-Tools CP-SAT) over the
existing unified DFS player pool (dfs/player_pool.py). This package
never scores or re-scores players -- it only selects and arranges
already-projected, active players into legal DraftKings lineups. It
never reads evaluation/ (postgame results) -- see
tests/test_architecture_separation.py.
"""
