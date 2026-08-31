"""NFL M6A Phase 9 -- cross-dataset consistency checks for one real
season/week, across the five raw snapshots already ingested. Pure set
membership / exact-ID comparison throughout -- no fuzzy matching
anywhere in this module (that is explicitly out of scope until M6B's
identity crosswalk, and even there only as a human-reviewed step)."""

from dataclasses import asdict, dataclass
from typing import List

import polars as pl


@dataclass
class ConsistencyReport:
    season: int
    week: int
    schedule_teams: int
    team_stats_teams: int
    teams_in_schedule_not_team_stats: List[str]
    teams_in_team_stats_not_schedule: List[str]
    weekly_stat_teams_not_in_schedule: List[str]
    roster_weekly_gsis_matched: int
    roster_weekly_gsis_unmatched: int
    pbp_game_ids_not_in_schedule: List[str]
    contamination_issues: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


def check_week_consistency(
    season: int, week: int,
    schedules_df: pl.DataFrame, rosters_df: pl.DataFrame,
    weekly_player_stats_df: pl.DataFrame, team_stats_df: pl.DataFrame, play_by_play_df: pl.DataFrame,
) -> ConsistencyReport:
    schedule_week = schedules_df.filter(pl.col("week") == week)
    schedule_teams = set(schedule_week["home_team"].to_list()) | set(schedule_week["away_team"].to_list())
    schedule_game_ids = set(schedule_week["game_id"].to_list())

    team_stats_teams = set(team_stats_df["team"].to_list())
    weekly_stat_teams = set(weekly_player_stats_df.filter(pl.col("team").is_not_null())["team"].to_list())

    roster_week = rosters_df.filter(pl.col("week") == week)
    roster_gsis = set(roster_week.filter((pl.col("gsis_id").is_not_null()) & (pl.col("gsis_id") != ""))["gsis_id"].to_list())
    weekly_stat_player_ids = set(weekly_player_stats_df.filter(pl.col("player_id").is_not_null())["player_id"].to_list())
    matched = roster_gsis & weekly_stat_player_ids
    unmatched = weekly_stat_player_ids - roster_gsis

    pbp_game_ids = set(play_by_play_df["game_id"].to_list())

    contamination: List[str] = []
    if (schedule_week["week"] != week).any():
        contamination.append("schedules: rows found with week != requested week after filter")
    for name, df, col in [("weekly_player_stats", weekly_player_stats_df, "week"), ("team_stats", team_stats_df, "week"), ("play_by_play", play_by_play_df, "week")]:
        bad = df.filter((pl.col(col) != week) | (pl.col("season") != season))
        if bad.height:
            contamination.append(f"{name}: {bad.height} row(s) with season/week != ({season}, {week})")

    return ConsistencyReport(
        season=season, week=week,
        schedule_teams=len(schedule_teams), team_stats_teams=len(team_stats_teams),
        teams_in_schedule_not_team_stats=sorted(schedule_teams - team_stats_teams),
        teams_in_team_stats_not_schedule=sorted(team_stats_teams - schedule_teams),
        weekly_stat_teams_not_in_schedule=sorted(weekly_stat_teams - schedule_teams),
        roster_weekly_gsis_matched=len(matched), roster_weekly_gsis_unmatched=len(unmatched),
        pbp_game_ids_not_in_schedule=sorted(pbp_game_ids - schedule_game_ids),
        contamination_issues=contamination,
    )
