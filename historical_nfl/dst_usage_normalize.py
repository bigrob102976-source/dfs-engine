"""NFL M8 -- builds NflDstUsageRecord rows from real M6A team_stats and
schedules data for one season/week. See dst_usage_models.py's module
docstring for exact field provenance.

fumble_recovery_opp on load_team_stats() is deliberately NOT used for a
fumbles_recovered feature: its exact semantics aren't confirmed (no data
dictionary shipped with this nflreadpy version), and this milestone's
explicit "do not invent fields the source does not contain" instruction
means an ambiguous column is left unused rather than guessed."""

from typing import Dict, List, Optional, Tuple

from historical_nfl.dst_usage_models import SOURCE_TEAM_STATS_DERIVED, NflDstUsageRecord


def _team_stats_by_team(team_stats_rows: List[dict]) -> Dict[str, dict]:
    return {row["team"]: row for row in team_stats_rows if row.get("team")}


def _scores_by_game(schedule_rows: List[dict]) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
    """{game_id -> (home_score, away_score)}."""
    result: Dict[str, Tuple[Optional[int], Optional[int]]] = {}
    for row in schedule_rows:
        game_id = row.get("game_id")
        if game_id:
            result[game_id] = (row.get("home_score"), row.get("away_score"))
    return result


def build_dst_usage_records(
    season: int, week: int,
    team_stats_rows: List[dict], schedule_rows: List[dict],
    fetched_at: str,
) -> List[NflDstUsageRecord]:
    """One record per real team_stats row (every team that played that
    week). points_allowed/yards_allowed are None when the game's
    schedule/opponent row can't be found -- never guessed."""
    by_team = _team_stats_by_team(team_stats_rows)
    scores = _scores_by_game(schedule_rows)

    # game_id -> {home_team, away_team} inferred from the schedule rows
    # themselves (real, structural -- never guessed).
    game_teams: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    for row in schedule_rows:
        gid = row.get("game_id")
        if gid:
            game_teams[gid] = (row.get("home_team"), row.get("away_team"))

    records: List[NflDstUsageRecord] = []
    for team, row in by_team.items():
        game_id = row.get("game_id")
        opponent = row.get("opponent_team")

        points_allowed = None
        if game_id in scores and game_id in game_teams:
            home_team, away_team = game_teams[game_id]
            home_score, away_score = scores[game_id]
            if team == home_team:
                points_allowed = away_score
            elif team == away_team:
                points_allowed = home_score

        yards_allowed = None
        opponent_row = by_team.get(opponent) if opponent else None
        if opponent_row is not None:
            opp_pass = opponent_row.get("passing_yards")
            opp_rush = opponent_row.get("rushing_yards")
            if opp_pass is not None and opp_rush is not None:
                yards_allowed = opp_pass + opp_rush

        records.append(NflDstUsageRecord(
            team=team, opponent=opponent, season=season, week=week, game_id=game_id,
            sacks=row.get("def_sacks"), interceptions=row.get("def_interceptions"),
            defensive_tds=row.get("def_tds"),
            points_allowed=points_allowed, yards_allowed=yards_allowed,
            source=SOURCE_TEAM_STATS_DERIVED, source_provenance=SOURCE_TEAM_STATS_DERIVED,
            ingested_at=fetched_at,
        ))

    return records
