"""NFL M11 -- builds NflTeamOffenseRecord rows from real M6A team_stats
and schedules data. Mirrors historical_nfl/dst_usage_normalize.py's
exact points_scored derivation."""

from typing import Dict, List, Optional, Tuple

from historical_nfl.team_offense_models import NflTeamOffenseRecord


def _team_stats_by_team(team_stats_rows: List[dict]) -> Dict[str, dict]:
    return {row["team"]: row for row in team_stats_rows if row.get("team")}


def _scores_by_game(schedule_rows: List[dict]) -> Dict[str, Tuple[Optional[int], Optional[int]]]:
    return {r["game_id"]: (r.get("home_score"), r.get("away_score")) for r in schedule_rows if r.get("game_id")}


def build_team_offense_records(
    season: int, week: int, team_stats_rows: List[dict], schedule_rows: List[dict], fetched_at: str,
) -> List[NflTeamOffenseRecord]:
    by_team = _team_stats_by_team(team_stats_rows)
    scores = _scores_by_game(schedule_rows)
    game_teams = {r["game_id"]: (r.get("home_team"), r.get("away_team")) for r in schedule_rows if r.get("game_id")}

    records: List[NflTeamOffenseRecord] = []
    for team, row in by_team.items():
        game_id = row.get("game_id")
        points_scored = None
        if game_id in scores and game_id in game_teams:
            home_team, away_team = game_teams[game_id]
            home_score, away_score = scores[game_id]
            if team == home_team:
                points_scored = home_score
            elif team == away_team:
                points_scored = away_score

        pass_yards = row.get("passing_yards")
        rush_yards = row.get("rushing_yards")
        total_yards = pass_yards + rush_yards if pass_yards is not None and rush_yards is not None else None

        interceptions = row.get("passing_interceptions")
        fumbles_lost = row.get("fumbles_lost_total")
        turnovers = interceptions + fumbles_lost if interceptions is not None and fumbles_lost is not None else None

        records.append(NflTeamOffenseRecord(
            team=team, opponent=row.get("opponent_team"), season=season, week=week, game_id=game_id,
            points_scored=points_scored, total_yards=total_yards, turnovers=turnovers,
            sacks_allowed=row.get("sacks_suffered"), pass_attempts=row.get("attempts"), rush_attempts=row.get("carries"),
            ingested_at=fetched_at,
        ))
    return records
