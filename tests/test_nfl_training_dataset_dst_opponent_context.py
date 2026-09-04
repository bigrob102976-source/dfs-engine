"""NFL M11 -- targeted tests for build_dst_training_rows' opponent-
context wiring (historical_nfl/team_offense_rolling.py attached via the
optional all_team_offense_records parameter)."""

from historical_nfl.team_offense_models import NflTeamOffenseRecord
from nfl.training_dataset import build_dst_training_rows

SEASON = 2025


def _team_stats_row(team="PHI", opponent="DAL", game_id="g6", def_sacks=1.0):
    return {"team": team, "opponent_team": opponent, "game_id": game_id, "def_sacks": def_sacks, "def_interceptions": 0, "def_safeties": 0, "def_fg_blocks": 0, "def_pat_blocks": 0, "def_punt_blocks": 0, "def_tds": 0, "special_teams_tds": 0}


def _schedule_row(game_id="g6", home="PHI", away="DAL"):
    return {"game_id": game_id, "home_team": home, "away_team": away, "home_score": 24, "away_score": 17, "home_rest": 7, "away_rest": 7}


def test_opponent_context_absent_when_not_provided_backward_compatible():
    rows = build_dst_training_rows(SEASON, 6, [_team_stats_row()], [], [], [_schedule_row()])
    assert not any(k.startswith("opponent_") for k in rows[0].rolling_features)


def test_opponent_context_present_and_leakage_safe_when_provided():
    """DAL (PHI's Week 6 opponent) has real offensive history in weeks
    1-5 -- Week 6+ must never leak into the opponent_* features."""
    opp_records = [NflTeamOffenseRecord(team="DAL", opponent="X", season=SEASON, week=w, game_id=f"g{w}", points_scored=w * 10) for w in range(1, 8)]
    rows = build_dst_training_rows(SEASON, 6, [_team_stats_row(team="PHI", opponent="DAL")], [], [], [_schedule_row()], all_team_offense_records=opp_records)
    features = rows[0].rolling_features
    assert "opponent_points_scored_mean_last1" in features
    assert features["opponent_points_scored_mean_last1"] == 50.0  # DAL's week 5 (5*10), never week 6's 60 or later


def test_opponent_context_uses_correct_opponent_not_own_team():
    """PHI's own history must never be mistaken for its opponent DAL's."""
    own_records = [NflTeamOffenseRecord(team="PHI", opponent="X", season=SEASON, week=w, game_id=f"g{w}", points_scored=999) for w in range(1, 6)]
    opp_records = [NflTeamOffenseRecord(team="DAL", opponent="X", season=SEASON, week=w, game_id=f"g{w}", points_scored=10) for w in range(1, 6)]
    rows = build_dst_training_rows(SEASON, 6, [_team_stats_row(team="PHI", opponent="DAL")], [], [], [_schedule_row()], all_team_offense_records=own_records + opp_records)
    assert rows[0].rolling_features["opponent_points_scored_mean_last1"] == 10.0  # DAL's, never PHI's 999
