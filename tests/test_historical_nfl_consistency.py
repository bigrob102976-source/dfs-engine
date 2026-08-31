"""NFL M6A -- targeted tests for historical_nfl/consistency.py. Synthetic
fixtures only -- the real cross-dataset proof is the M6A final report's
live 2025 Week 1 reconciliation (100% GSIS match, zero mismatches)."""

import polars as pl

from historical_nfl.consistency import check_week_consistency

SEASON = 2025
WEEK = 1


def _base_frames():
    schedules = pl.DataFrame({
        "season": [SEASON], "week": [WEEK], "game_id": ["2025_01_DAL_PHI"], "home_team": ["PHI"], "away_team": ["DAL"],
    })
    rosters = pl.DataFrame({"season": [SEASON], "week": [WEEK], "gsis_id": ["00-0000001"], "team": ["PHI"]})
    weekly_stats = pl.DataFrame({"season": [SEASON], "week": [WEEK], "player_id": ["00-0000001"], "team": ["PHI"]})
    team_stats = pl.DataFrame({"season": [SEASON, SEASON], "week": [WEEK, WEEK], "team": ["PHI", "DAL"]})
    pbp = pl.DataFrame({"season": [SEASON], "week": [WEEK], "game_id": ["2025_01_DAL_PHI"]})
    return schedules, rosters, weekly_stats, team_stats, pbp


def test_fully_consistent_week_reports_zero_mismatches():
    schedules, rosters, weekly_stats, team_stats, pbp = _base_frames()
    report = check_week_consistency(SEASON, WEEK, schedules, rosters, weekly_stats, team_stats, pbp)
    assert report.teams_in_schedule_not_team_stats == []
    assert report.teams_in_team_stats_not_schedule == []
    assert report.weekly_stat_teams_not_in_schedule == []
    assert report.roster_weekly_gsis_matched == 1
    assert report.roster_weekly_gsis_unmatched == 0
    assert report.pbp_game_ids_not_in_schedule == []
    assert report.contamination_issues == []


def test_team_stats_missing_a_schedule_team_is_reported():
    schedules, rosters, weekly_stats, team_stats, pbp = _base_frames()
    team_stats = pl.DataFrame({"season": [SEASON], "week": [WEEK], "team": ["SEA"]})  # wrong team entirely
    report = check_week_consistency(SEASON, WEEK, schedules, rosters, weekly_stats, team_stats, pbp)
    assert "PHI" in report.teams_in_schedule_not_team_stats
    assert "SEA" in report.teams_in_team_stats_not_schedule


def test_unmatched_weekly_stat_player_reported_never_fuzzy_matched():
    schedules, rosters, weekly_stats, team_stats, pbp = _base_frames()
    weekly_stats = pl.DataFrame({"season": [SEASON], "week": [WEEK], "player_id": ["00-9999999"], "team": ["PHI"]})  # not on the roster
    report = check_week_consistency(SEASON, WEEK, schedules, rosters, weekly_stats, team_stats, pbp)
    assert report.roster_weekly_gsis_matched == 0
    assert report.roster_weekly_gsis_unmatched == 1


def test_pbp_game_id_not_in_schedule_reported():
    schedules, rosters, weekly_stats, team_stats, pbp = _base_frames()
    pbp = pl.DataFrame({"season": [SEASON], "week": [WEEK], "game_id": ["2099_01_XXX_YYY"]})
    report = check_week_consistency(SEASON, WEEK, schedules, rosters, weekly_stats, team_stats, pbp)
    assert report.pbp_game_ids_not_in_schedule == ["2099_01_XXX_YYY"]


def test_cross_week_contamination_detected():
    schedules, rosters, weekly_stats, team_stats, pbp = _base_frames()
    weekly_stats = pl.DataFrame({"season": [SEASON], "week": [2], "player_id": ["00-0000001"], "team": ["PHI"]})  # wrong week snuck in
    report = check_week_consistency(SEASON, WEEK, schedules, rosters, weekly_stats, team_stats, pbp)
    assert any("weekly_player_stats" in issue for issue in report.contamination_issues)


def test_cross_season_contamination_detected():
    schedules, rosters, weekly_stats, team_stats, pbp = _base_frames()
    team_stats = pl.DataFrame({"season": [2024], "week": [WEEK], "team": ["PHI"]})  # wrong season snuck in
    report = check_week_consistency(SEASON, WEEK, schedules, rosters, weekly_stats, team_stats, pbp)
    assert any("team_stats" in issue for issue in report.contamination_issues)


def test_missing_gsis_or_player_id_never_counted_as_a_match():
    schedules, rosters, weekly_stats, team_stats, pbp = _base_frames()
    rosters = pl.DataFrame({"season": [SEASON], "week": [WEEK], "gsis_id": [""], "team": ["PHI"]})
    weekly_stats = pl.DataFrame({"season": [SEASON], "week": [WEEK], "player_id": [None], "team": ["PHI"]}, schema_overrides={"player_id": pl.Utf8})
    report = check_week_consistency(SEASON, WEEK, schedules, rosters, weekly_stats, team_stats, pbp)
    assert report.roster_weekly_gsis_matched == 0
    assert report.roster_weekly_gsis_unmatched == 0
