"""NFL M11 -- targeted tests for team_offense_normalize.py and
team_offense_rolling.py (the DST opponent-context layer)."""

from historical_nfl.team_offense_models import NflTeamOffenseRecord
from historical_nfl.team_offense_normalize import build_team_offense_records
from historical_nfl.team_offense_rolling import compute_team_offense_rolling_features

SEASON, WEEK = 2025, 1


def _team_stats_row(team, opponent, game_id, passing_yards=200, rushing_yards=100, passing_interceptions=1, fumbles_lost_total=1, sacks_suffered=2.0, attempts=30, carries=25):
    return {"team": team, "opponent_team": opponent, "game_id": game_id, "passing_yards": passing_yards, "rushing_yards": rushing_yards, "passing_interceptions": passing_interceptions, "fumbles_lost_total": fumbles_lost_total, "sacks_suffered": sacks_suffered, "attempts": attempts, "carries": carries}


def _schedule_row(game_id, home, away, home_score=24, away_score=20):
    return {"game_id": game_id, "home_team": home, "away_team": away, "home_score": home_score, "away_score": away_score}


def test_total_yards_and_turnovers_derived_correctly():
    team_stats = [_team_stats_row("DAL", "PHI", "g1", passing_yards=200, rushing_yards=100, passing_interceptions=2, fumbles_lost_total=1)]
    records = build_team_offense_records(SEASON, WEEK, team_stats, [], "t0")
    r = records[0]
    assert r.total_yards == 300
    assert r.turnovers == 3


def test_points_scored_derived_from_schedule():
    team_stats = [_team_stats_row("PHI", "DAL", "g1"), _team_stats_row("DAL", "PHI", "g1")]
    schedule = [_schedule_row("g1", home="PHI", away="DAL", home_score=24, away_score=20)]
    records = build_team_offense_records(SEASON, WEEK, team_stats, schedule, "t0")
    by_team = {r.team: r for r in records}
    assert by_team["PHI"].points_scored == 24
    assert by_team["DAL"].points_scored == 20


def test_opponent_rolling_leakage_boundary():
    records = [NflTeamOffenseRecord(team="DAL", opponent="X", season=SEASON, week=w, game_id=f"g{w}", points_scored=w * 10) for w in range(1, 8)]
    features = compute_team_offense_rolling_features(records, "DAL", as_of_week=5, windows=(1,))
    assert features["opponent_points_scored_mean_last1"] == 40.0  # week 4's value, never week 5+


def test_opponent_no_history_returns_none():
    features = compute_team_offense_rolling_features([], "DAL", as_of_week=1, windows=(1, 3))
    assert features["opponent_points_scored_mean_last1"] is None
    assert features["opponent_weeks_of_history"] == 0
