"""Centralized DraftKings Classic MLB roster rules.

DraftKings salary-export CSVs do not carry contest structure (roster
slots, salary cap) -- that information lives on the contest lobby page,
not in the file this milestone parses. These constants are the publicly
documented DraftKings Classic MLB rules as of this writing, kept in ONE
named place (not scattered through the optimizer that will consume them
next milestone) precisely so the assumption is easy to find and correct
later if DraftKings changes it or a contest turns out to use a variant
ruleset. If a future CSV/contest-metadata source ever supplies these
values directly, that source should win over this fallback.

Showdown/Captain Mode is a different ruleset entirely and is explicitly
out of scope for this milestone -- Classic MLB only.
"""

DK_CLASSIC_SALARY_CAP = 50000

# Slot name -> (how many roster spots, which DK position labels satisfy it).
# Order matters only for display/iteration convenience; it has no effect
# on feasibility checking.
DK_CLASSIC_ROSTER_SLOTS = [
    {"slot": "P", "count": 2, "eligible_positions": ["P"]},
    {"slot": "C", "count": 1, "eligible_positions": ["C"]},
    {"slot": "1B", "count": 1, "eligible_positions": ["1B"]},
    {"slot": "2B", "count": 1, "eligible_positions": ["2B"]},
    {"slot": "3B", "count": 1, "eligible_positions": ["3B"]},
    {"slot": "SS", "count": 1, "eligible_positions": ["SS"]},
    {"slot": "OF", "count": 3, "eligible_positions": ["OF"]},
]

DK_ROSTER_SIZE = sum(s["count"] for s in DK_CLASSIC_ROSTER_SLOTS)  # 10

# Documented DraftKings Classic MLB rule: a valid lineup must include
# players from at least this many different games. This is a real
# published DK rule, not an invented constraint -- kept here, explicitly
# named, so the feasibility checker can apply or ignore it deliberately
# rather than the rule silently hiding inside optimizer code later.
DK_MIN_GAMES_REPRESENTED = 2

# Documented DraftKings Classic MLB rule (Milestone 9): a lineup may not
# include more than this many HITTERS from the same team. Pitchers are
# never counted against this limit. Added here (not in optimizer/) so the
# solver, validator, and any future consumer share one definition instead
# of each hardcoding "5".
DK_MAX_HITTERS_PER_TEAM = 5
