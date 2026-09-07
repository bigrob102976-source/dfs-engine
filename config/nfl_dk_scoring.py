"""NFL M9 -- real DraftKings NFL Classic scoring constants.

Source: DraftKings' own official rules page (draftkings.com/help/rules/nfl)
returns HTTP 403 (Cloudflare bot-management, the same class of block
documented in research/game_environment/providers/sportsgameodds.py --
not an auth issue, a transport-layer one). Verified instead against TWO
independent, cross-consistent secondary sources: rotogrinders.com's NFL
site-scoring-comparison table (a DraftKings-specific column, explicitly
labeled) and a Heavy.com DraftKings rules writeup -- both agree on every
value below. Not primary-sourced; if a discrepancy is ever found against
DK's own page, this file is the one to correct.

Mirrors config/scoring_config.py's (MLB) exact discipline: one
authoritative dict, never duplicated or hand-copied elsewhere."""

DK_NFL_OFFENSE_SCORING = {
    "passing_yard": 0.04,       # 1 point per 25 yards
    "passing_td": 4.0,
    "passing_interception": -1.0,
    "passing_300_yard_bonus": 3.0,
    "passing_300_yard_threshold": 300,

    "rushing_yard": 0.1,        # 1 point per 10 yards
    "rushing_td": 6.0,
    "rushing_100_yard_bonus": 3.0,
    "rushing_100_yard_threshold": 100,

    "reception": 1.0,           # full PPR
    "receiving_yard": 0.1,      # 1 point per 10 yards
    "receiving_td": 6.0,
    "receiving_100_yard_bonus": 3.0,
    "receiving_100_yard_threshold": 100,

    "fumble_lost": -1.0,
    "two_point_conversion": 2.0,  # any 2pt conversion the player scored/threw
}

DK_NFL_DST_SCORING = {
    "sack": 1.0,
    "interception": 2.0,
    "fumble_recovery": 2.0,
    "safety": 2.0,
    "blocked_kick": 2.0,
    "defensive_or_return_td": 6.0,
}

# Points-allowed bracket -> bonus points. Evaluated as "points_allowed in
# [lo, hi]" (hi=None means unbounded above), first matching bracket wins.
DK_NFL_DST_POINTS_ALLOWED_BRACKETS = (
    (0, 0, 10.0),
    (1, 6, 7.0),
    (7, 13, 4.0),
    (14, 20, 1.0),
    (21, 27, 0.0),
    (28, 34, -1.0),
    (35, None, -4.0),
)


def points_allowed_bonus(points_allowed: int) -> float:
    for lo, hi, bonus in DK_NFL_DST_POINTS_ALLOWED_BRACKETS:
        if points_allowed >= lo and (hi is None or points_allowed <= hi):
            return bonus
    raise ValueError(f"points_allowed={points_allowed!r} did not match any real bracket (should be impossible for a non-negative int).")
