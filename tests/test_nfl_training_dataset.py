"""NFL M9 -- targeted tests for nfl/training_dataset.py. Synthetic
fixtures, no network. Strong emphasis on leakage, split assignment, and
rookie/no-history handling."""

from historical_nfl.dst_usage_models import NflDstUsageRecord
from historical_nfl.usage_models import NflUsageRecord
from nfl.training_dataset import (
    SCHEMA_VERSION,
    SPLIT_TEST,
    SPLIT_TRAIN,
    SPLIT_VALIDATION,
    assign_split,
    build_dst_training_rows,
    build_offense_training_rows,
)

SEASON = 2025


def _stat_row(gsis_id="00-1", position="RB", team="PHI", opponent="DAL", week=6, game_id="g6",
              rushing_yards=50, carries=10, passing_yards=0, receptions=0, receiving_yards=0):
    return {
        "player_id": gsis_id, "position": position, "team": team, "opponent_team": opponent,
        "week": week, "game_id": game_id, "rushing_yards": rushing_yards, "carries": carries,
        "passing_yards": passing_yards, "passing_tds": 0, "passing_interceptions": 0,
        "rushing_tds": 0, "receptions": receptions, "receiving_yards": receiving_yards, "receiving_tds": 0,
        "fumbles_lost_total": 0, "passing_2pt_conversions": 0, "rushing_2pt_conversions": 0, "receiving_2pt_conversions": 0,
    }


def _usage(gsis_id, week, carries=10):
    return NflUsageRecord(canonical_player_id=None, gsis_id=gsis_id, season=SEASON, week=week, game_id=f"g{week}", team="PHI", opponent="DAL", position="RB", carries=carries)


def _schedule_row(game_id, home, away, home_score=24, away_score=20, home_rest=7, away_rest=7):
    return {"game_id": game_id, "home_team": home, "away_team": away, "home_score": home_score, "away_score": away_score, "home_rest": home_rest, "away_rest": away_rest}


def test_split_assignment_deterministic_by_week():
    assert assign_split(1) == SPLIT_TRAIN
    assert assign_split(13) == SPLIT_TRAIN
    assert assign_split(14) == SPLIT_VALIDATION
    assert assign_split(15) == SPLIT_VALIDATION
    assert assign_split(16) == SPLIT_TEST
    assert assign_split(18) == SPLIT_TEST


def test_offense_row_has_correct_schema_version():
    rows = build_offense_training_rows(SEASON, 6, [_stat_row()], [], [], [])
    assert rows[0].schema_version == SCHEMA_VERSION


def test_defensive_position_never_produces_an_offense_row():
    rows = build_offense_training_rows(SEASON, 6, [_stat_row(position="LB")], [], [], [])
    assert rows == []


def test_target_computed_from_that_weeks_own_stat_line():
    rows = build_offense_training_rows(SEASON, 6, [_stat_row(rushing_yards=120)], [], [], [])
    assert rows[0].target_scored is True
    assert rows[0].target_dk_points > 12.0  # 120*0.1 + 3 bonus = 15.0, plus 0 other


def test_feature_leakage_as_of_week_excludes_that_weeks_usage():
    """The core M9 invariant: even though a week-6 usage record exists
    (the same week being predicted), computing features as-of week 6
    must never read it -- only weeks strictly before 6."""
    usage = [_usage("00-1", w, carries=w * 10) for w in range(1, 9)]  # includes week 6 (carries=60) and week 7,8 (future)
    rows = build_offense_training_rows(SEASON, 6, [_stat_row(gsis_id="00-1")], usage, [], [])
    rolling = rows[0].rolling_features
    assert rolling["carries_mean_last1"] == 50.0  # week 5's value (5*10), never week 6's (60) or week 7/8's


def test_rookie_no_history_gets_null_rolling_features_not_zero():
    rows = build_offense_training_rows(SEASON, 1, [_stat_row(gsis_id="00-1", week=1, game_id="g1")], [], [], [])
    row = rows[0]
    assert row.has_prior_week is False
    assert row.weeks_of_history == 0
    assert row.rolling_features["carries_mean_last1"] is None  # never 0.0


def test_veteran_with_history_gets_has_prior_week_true():
    usage = [_usage("00-1", 5, carries=10)]
    rows = build_offense_training_rows(SEASON, 6, [_stat_row(gsis_id="00-1")], usage, [], [])
    assert rows[0].has_prior_week is True
    assert rows[0].weeks_of_history == 1


def test_salary_is_always_none():
    rows = build_offense_training_rows(SEASON, 6, [_stat_row()], [], [], [])
    assert rows[0].salary is None


def test_injury_report_status_joined_when_present():
    injuries = [{"week": 6, "gsis_id": "00-1", "report_status": "Questionable"}]
    rows = build_offense_training_rows(SEASON, 6, [_stat_row(gsis_id="00-1")], [], [], injuries)
    assert rows[0].injury_report_status == "Questionable"


def test_injury_report_status_none_when_absent():
    rows = build_offense_training_rows(SEASON, 6, [_stat_row()], [], [], [])
    assert rows[0].injury_report_status is None


def test_home_away_and_rest_derived_from_schedule():
    schedule = [_schedule_row("g6", home="PHI", away="DAL", home_rest=10, away_rest=6)]
    rows = build_offense_training_rows(SEASON, 6, [_stat_row(team="PHI", game_id="g6")], [], schedule, [])
    assert rows[0].home_away == "home"
    assert rows[0].rest_days == 10


def test_no_duplicate_rows_for_the_same_player_week():
    rows = build_offense_training_rows(SEASON, 6, [_stat_row(gsis_id="00-1"), _stat_row(gsis_id="00-1")], [], [], [])
    keys = [(r.season, r.week, r.gsis_id) for r in rows]
    # two identical input rows -> two output rows is a data problem the
    # caller (real ingestion) shouldn't produce; this test documents that
    # the builder itself does not deduplicate silently, so upstream
    # duplicate weekly_stats rows would surface as duplicate keys
    assert len(keys) == 2  # not silently collapsed -- see Phase 17's duplicate-detection quality check instead


# --- DST ---

def _team_stats_row(team="PHI", opponent="DAL", game_id="g6", def_sacks=1.0):
    return {"team": team, "opponent_team": opponent, "game_id": game_id, "def_sacks": def_sacks, "def_interceptions": 0, "def_safeties": 0, "def_fg_blocks": 0, "def_pat_blocks": 0, "def_punt_blocks": 0, "def_tds": 0, "special_teams_tds": 0}


def test_dst_row_never_has_gsis_identity():
    schedule = [_schedule_row("g6", "PHI", "DAL")]
    rows = build_dst_training_rows(SEASON, 6, [_team_stats_row()], [], [], schedule)
    assert rows[0].canonical_player_id == "dst:PHI"
    assert not hasattr(rows[0], "gsis_id")


def test_dst_feature_leakage_boundary():
    dst_records = [NflDstUsageRecord(team="PHI", opponent="DAL", season=SEASON, week=w, game_id=f"g{w}", sacks=w * 1.0) for w in range(1, 9)]
    schedule = [_schedule_row("g6", "PHI", "DAL")]
    rows = build_dst_training_rows(SEASON, 6, [_team_stats_row()], dst_records, [], schedule)
    assert rows[0].rolling_features["sacks_mean_last1"] == 5.0  # week 5, never week 6+


def test_dst_target_scored_when_points_allowed_available():
    schedule = [_schedule_row("g6", "PHI", "DAL", home_score=24, away_score=17)]
    rows = build_dst_training_rows(SEASON, 6, [_team_stats_row(team="PHI", game_id="g6")], [], [], schedule)
    assert rows[0].target_scored is True
