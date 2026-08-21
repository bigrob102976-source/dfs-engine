"""Milestone 32.0 -- isolated historical MLB data research/proof-of-concept
area for the future Big Money DFS native projection *training* pipeline.

This package is deliberately separate from every LIVE projection path
(native_projections/, projection_engine/, agents/, dfs/pool_builder.py,
the optimizer). Nothing in the current production pipeline imports
anything from here, and nothing here is imported by the current
production pipeline -- see tests/test_architecture_separation.py's
PREGAME_PACKAGE_DIRS convention, which this package deliberately does
NOT join yet (it isn't part of the pregame slate pipeline at all, live
or historical).

Scope as of M32.0: audit/proof-of-concept only. No model is trained
here. No optimizer, Native, or AI projection math is read or written.
"""
