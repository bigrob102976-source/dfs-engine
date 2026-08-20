"""Milestone 31.2 -- UNOFFICIAL DraftKings development data provider.

Every module under this package talks to (or normalizes data from)
DraftKings' undocumented public JSON endpoints, used ONLY to unblock
Big Money DFS development with real, broad, multi-sport DFS data while
no licensed provider is in place. This is explicitly temporary and
replaceable -- see draftkings_unofficial/README.md.

The endpoint contract is NOT documented by DraftKings and can change
without notice. Every response shape here was confirmed by direct live
requests during this milestone (not assumed from third-party docs from
2021, which this milestone found to still roughly match the current
shape but not exactly -- see the README's "Known Limitations" section).
"""
