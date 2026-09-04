"""NFL M8 -- targeted tests for historical_nfl/dst_usage_normalize.py.
Synthetic fixtures, real field names."""

from historical_nfl.dst_usage_normalize import build_dst_usage_records

SEASON, WEEK = 2025, 1
FETCHED_AT = "2026-09-04T00:00:00+00:00"


def _team_stats_row(team, opponent, game_id, def_sacks=2.0, def_interceptions=1, def_tds=0,
                     passing_yards=200, rushing_yards=100):
    return {
        "team": team, "opponent_team": opponent, "game_id": game_id,
        "def_sacks": def_sacks, "def_interceptions": def_interceptions, "def_tds": def_tds,
        "passing_yards": passing_yards, "rushing_yards": rushing_yards,
    }


def _schedule_row(game_id, home_team, away_team, home_score, away_score):
    return {"game_id": game_id, "home_team": home_team, "away_team": away_team, "home_score": home_score, "away_score": away_score}


def test_sacks_interceptions_tds_are_direct_passthroughs():
    team_stats = [_team_stats_row("PHI", "DAL", "g1", def_sacks=3.0, def_interceptions=2, def_tds=1)]
    records = build_dst_usage_records(SEASON, WEEK, team_stats, [], FETCHED_AT)
    r = records[0]
    assert r.sacks == 3.0
    assert r.interceptions == 2
    assert r.defensive_tds == 1


def test_points_allowed_derived_from_opponents_schedule_score():
    team_stats = [
        _team_stats_row("PHI", "DAL", "g1"),
        _team_stats_row("DAL", "PHI", "g1"),
    ]
    schedule = [_schedule_row("g1", home_team="PHI", away_team="DAL", home_score=24, away_score=20)]
    records = build_dst_usage_records(SEASON, WEEK, team_stats, schedule, FETCHED_AT)
    by_team = {r.team: r for r in records}
    assert by_team["PHI"].points_allowed == 20  # PHI (home) allowed DAL's (away) score
    assert by_team["DAL"].points_allowed == 24  # DAL (away) allowed PHI's (home) score


def test_yards_allowed_derived_from_opponents_own_offensive_row():
    team_stats = [
        _team_stats_row("PHI", "DAL", "g1", passing_yards=200, rushing_yards=100),
        _team_stats_row("DAL", "PHI", "g1", passing_yards=150, rushing_yards=80),
    ]
    records = build_dst_usage_records(SEASON, WEEK, team_stats, [], FETCHED_AT)
    by_team = {r.team: r for r in records}
    assert by_team["PHI"].yards_allowed == 230  # DAL's own 150+80 offense
    assert by_team["DAL"].yards_allowed == 300  # PHI's own 200+100 offense


def test_points_allowed_none_when_schedule_row_missing():
    team_stats = [_team_stats_row("PHI", "DAL", "g1")]
    records = build_dst_usage_records(SEASON, WEEK, team_stats, [], FETCHED_AT)
    assert records[0].points_allowed is None


def test_yards_allowed_none_when_opponent_row_missing():
    team_stats = [_team_stats_row("PHI", "DAL", "g1")]
    records = build_dst_usage_records(SEASON, WEEK, team_stats, [], FETCHED_AT)
    assert records[0].yards_allowed is None


def test_one_record_per_team_no_fake_gsis_identity():
    team_stats = [_team_stats_row("PHI", "DAL", "g1"), _team_stats_row("DAL", "PHI", "g1")]
    records = build_dst_usage_records(SEASON, WEEK, team_stats, [], FETCHED_AT)
    assert len(records) == 2
    for r in records:
        assert not hasattr(r, "gsis_id")
        assert r.team in ("PHI", "DAL")
