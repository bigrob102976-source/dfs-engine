"""DraftKings salary ingestion + unified DFS player pool (Milestone 8).

This package reads a user-provided DraftKings salary CSV plus the
existing Research Package and pregame prediction snapshots, and joins
them into one reproducible, immutable DFS player pool. It does not
score players itself (that's agents/pitcher_agent.py and
agents/batter_agent.py, unmodified) and it never reads evaluation/
(postgame results) -- see tests/test_architecture_separation.py.
"""
