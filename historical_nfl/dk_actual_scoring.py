"""NFL M9 -- computes REAL, observed DraftKings NFL Classic fantasy
points from a real postgame stat line. This is a TARGET (label)
computation, not a feature -- it is only ever applied to the completed
week's own raw box score, never fed backward into a pre-game feature
(see historical_nfl/usage_rolling.py for the feature-side leakage
boundary, which is a fully separate concern from this module).

Operates directly on the raw nflreadpy.load_player_stats() /
load_team_stats() row dicts (same shape used throughout historical_nfl/
ingest.py and usage_normalize.py), not on NflUsageRecord -- the box-score
fields NflUsageRecord carries (M8) are a deliberately narrower "usage
feature" set; interceptions thrown, fumbles lost, and 2pt conversions
are target-only inputs this module reads straight from the source row
rather than adding to the feature model.

Mirrors evaluation/dk_actual_scoring.py's (MLB) exact "explicit
not-scored rather than silent zero" discipline: every helper returns
{"scored": bool, "dfs_points": Optional[float], "breakdown": dict}."""

from typing import Dict, List, Optional

from config.nfl_dk_scoring import DK_NFL_DST_SCORING, DK_NFL_OFFENSE_SCORING, points_allowed_bonus

_OFFENSE_SCOREABLE_POSITIONS = {"QB", "RB", "WR", "TE"}


def calculate_actual_offense_dk_points(row: dict) -> dict:
    """`row` is one real nflreadpy.load_player_stats() row (a dict, e.g.
    from a polars DataFrame's .to_dicts()). Returns not-scored for a
    position this module doesn't cover (defensive players show up in
    the same weekly_player_stats rows -- see historical_nfl/usage_
    normalize.py's module docstring -- but have no offensive box score
    to score here)."""
    position = row.get("position")
    if position not in _OFFENSE_SCOREABLE_POSITIONS:
        return {"scored": False, "dfs_points": None, "breakdown": {}}

    dk = DK_NFL_OFFENSE_SCORING

    passing_yards = row.get("passing_yards") or 0
    passing_tds = row.get("passing_tds") or 0
    passing_interceptions = row.get("passing_interceptions") or 0

    rushing_yards = row.get("rushing_yards") or 0
    rushing_tds = row.get("rushing_tds") or 0

    receptions = row.get("receptions") or 0
    receiving_yards = row.get("receiving_yards") or 0
    receiving_tds = row.get("receiving_tds") or 0

    fumbles_lost = row.get("fumbles_lost_total") or 0

    two_pt_conversions = (
        (row.get("passing_2pt_conversions") or 0)
        + (row.get("rushing_2pt_conversions") or 0)
        + (row.get("receiving_2pt_conversions") or 0)
    )

    breakdown = {
        "passing_yard_points": round(passing_yards * dk["passing_yard"], 2),
        "passing_td_points": round(passing_tds * dk["passing_td"], 2),
        "passing_interception_points": round(passing_interceptions * dk["passing_interception"], 2),
        "passing_300_bonus_points": dk["passing_300_yard_bonus"] if passing_yards >= dk["passing_300_yard_threshold"] else 0.0,

        "rushing_yard_points": round(rushing_yards * dk["rushing_yard"], 2),
        "rushing_td_points": round(rushing_tds * dk["rushing_td"], 2),
        "rushing_100_bonus_points": dk["rushing_100_yard_bonus"] if rushing_yards >= dk["rushing_100_yard_threshold"] else 0.0,

        "reception_points": round(receptions * dk["reception"], 2),
        "receiving_yard_points": round(receiving_yards * dk["receiving_yard"], 2),
        "receiving_td_points": round(receiving_tds * dk["receiving_td"], 2),
        "receiving_100_bonus_points": dk["receiving_100_yard_bonus"] if receiving_yards >= dk["receiving_100_yard_threshold"] else 0.0,

        "fumble_lost_points": round(fumbles_lost * dk["fumble_lost"], 2),
        "two_point_conversion_points": round(two_pt_conversions * dk["two_point_conversion"], 2),
    }

    dfs_points = round(sum(breakdown.values()), 2)
    return {"scored": True, "dfs_points": dfs_points, "breakdown": breakdown}


def _defense_fumble_recoveries(team: str, pbp_rows: List[dict]) -> int:
    """Real, unambiguous PBP derivation (unlike load_team_stats()'s
    fumble_recovery_opp/own columns, whose exact semantics this project
    declined to guess -- see historical_nfl/dst_usage_normalize.py's
    module docstring): a fumble this team's DEFENSE recovered is any
    play-by-play row where fumble_recovery_1_team == team AND the team
    in possession at the time (posteam) was the OPPONENT, not this
    team -- i.e. a real takeaway, never this team recovering its own
    fumble."""
    count = 0
    for row in pbp_rows:
        recovering_team = row.get("fumble_recovery_1_team")
        posteam = row.get("posteam")
        if recovering_team == team and posteam is not None and posteam != team:
            count += 1
    return count


def calculate_actual_dst_dk_points(
    team: str, team_stats_row: Optional[dict], pbp_rows: List[dict], points_allowed: Optional[int],
) -> dict:
    """`team_stats_row` is one real nflreadpy.load_team_stats() row for
    `team` (its own defensive def_* columns -- see historical_nfl/
    dst_usage_normalize.py's module docstring for why these are
    confidently this team's OWN defensive stats, not stats committed
    against them). Not-scored when team_stats_row or points_allowed is
    missing -- never guessed."""
    if team_stats_row is None or points_allowed is None:
        return {"scored": False, "dfs_points": None, "breakdown": {}}

    dk = DK_NFL_DST_SCORING

    sacks = team_stats_row.get("def_sacks") or 0.0
    interceptions = team_stats_row.get("def_interceptions") or 0
    safeties = team_stats_row.get("def_safeties") or 0
    blocked_kicks = (
        (team_stats_row.get("def_fg_blocks") or 0)
        + (team_stats_row.get("def_pat_blocks") or 0)
        + (team_stats_row.get("def_punt_blocks") or 0)
    )
    # Defensive TDs (INT/fumble return) + special-teams TDs (kick/punt
    # return) -- both real, separate team_stats columns; DraftKings
    # scores every kind of return TD identically (6 pts), so both are
    # summed into one "defensive_or_return_td" bucket.
    defensive_or_return_tds = (team_stats_row.get("def_tds") or 0) + (team_stats_row.get("special_teams_tds") or 0)

    fumble_recoveries = _defense_fumble_recoveries(team, pbp_rows)

    breakdown = {
        "sack_points": round(sacks * dk["sack"], 2),
        "interception_points": round(interceptions * dk["interception"], 2),
        "fumble_recovery_points": round(fumble_recoveries * dk["fumble_recovery"], 2),
        "safety_points": round(safeties * dk["safety"], 2),
        "blocked_kick_points": round(blocked_kicks * dk["blocked_kick"], 2),
        "defensive_or_return_td_points": round(defensive_or_return_tds * dk["defensive_or_return_td"], 2),
        "points_allowed_bonus_points": points_allowed_bonus(points_allowed),
    }

    dfs_points = round(sum(breakdown.values()), 2)
    return {"scored": True, "dfs_points": dfs_points, "breakdown": breakdown}
