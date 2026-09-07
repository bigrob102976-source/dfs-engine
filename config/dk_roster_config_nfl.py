"""Centralized DraftKings Classic NFL roster rules.

Sibling to config/dk_roster_config.py (MLB) -- kept as a separate file
rather than turning that module into a sport-switching one, so MLB's
existing config stays byte-for-byte unchanged and this file can evolve
independently as NFL milestones progress.

Verified LIVE (NFL M1): /lineups/v1/gametypes/1/rules for the real
Classic DraftGroup 151307 (2026-09-13, 12 games) returned exactly QB,
RB, RB, WR, WR, WR, TE, FLEX, DST at a $50,000 cap -- not assumed from
public documentation.
"""

DK_NFL_CLASSIC_SALARY_CAP = 50000

# Slot name -> (how many roster spots, which base positions satisfy it).
# FLEX is its own distinct slot (DraftKings' own roster_slot_id 70 in
# the real payload) -- never collapsed into a base position, and never
# assumed eligible for QB/DST (see FLEX_ELIGIBLE_BASE_POSITIONS below).
DK_NFL_CLASSIC_ROSTER_SLOTS = [
    {"slot": "QB", "count": 1, "eligible_positions": ["QB"]},
    {"slot": "RB", "count": 2, "eligible_positions": ["RB"]},
    {"slot": "WR", "count": 3, "eligible_positions": ["WR"]},
    {"slot": "TE", "count": 1, "eligible_positions": ["TE"]},
    {"slot": "FLEX", "count": 1, "eligible_positions": ["RB", "WR", "TE"]},
    {"slot": "DST", "count": 1, "eligible_positions": ["DST"]},
]

DK_NFL_ROSTER_SIZE = sum(s["count"] for s in DK_NFL_CLASSIC_ROSTER_SLOTS)  # 9

DK_NFL_BASE_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "DST"})

# Documentation/assertion constant only -- the actual slot-fill decision
# (nfl/solver.py) always checks a canonical NflPlayer's own real
# `roster_slots` field (from nfl/pool_builder.py, itself derived from
# DraftKings' own roster_slot_id per player), never re-derives FLEX
# eligibility from base position alone. QB and DST are never FLEX-
# eligible -- confirmed live: rosterSlotId 70 (FLEX) only ever paired
# with RB/WR/TE across all 719 real players on DraftGroup 151307.
FLEX_ELIGIBLE_BASE_POSITIONS = frozenset({"RB", "WR", "TE"})
