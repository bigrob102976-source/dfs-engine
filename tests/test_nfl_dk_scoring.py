"""NFL M9 -- targeted tests for config/nfl_dk_scoring.py and
historical_nfl/dk_actual_scoring.py."""

from config.nfl_dk_scoring import points_allowed_bonus
from historical_nfl.dk_actual_scoring import calculate_actual_dst_dk_points, calculate_actual_offense_dk_points


def _row(position="QB", **overrides):
    row = {
        "position": position, "passing_yards": 0, "passing_tds": 0, "passing_interceptions": 0,
        "rushing_yards": 0, "rushing_tds": 0, "receptions": 0, "receiving_yards": 0, "receiving_tds": 0,
        "fumbles_lost_total": 0, "passing_2pt_conversions": 0, "rushing_2pt_conversions": 0, "receiving_2pt_conversions": 0,
    }
    row.update(overrides)
    return row


def test_defensive_position_row_is_not_scored():
    result = calculate_actual_offense_dk_points(_row(position="LB"))
    assert result["scored"] is False
    assert result["dfs_points"] is None


def test_passing_yards_and_td_scoring():
    result = calculate_actual_offense_dk_points(_row(passing_yards=250, passing_tds=2))
    assert result["breakdown"]["passing_yard_points"] == 10.0  # 250 * 0.04
    assert result["breakdown"]["passing_td_points"] == 8.0
    assert result["dfs_points"] == 18.0


def test_passing_300_yard_bonus_applies_at_exactly_300():
    below = calculate_actual_offense_dk_points(_row(passing_yards=299))
    at = calculate_actual_offense_dk_points(_row(passing_yards=300))
    assert below["breakdown"]["passing_300_bonus_points"] == 0.0
    assert at["breakdown"]["passing_300_bonus_points"] == 3.0


def test_interception_thrown_is_minus_one():
    result = calculate_actual_offense_dk_points(_row(passing_interceptions=2))
    assert result["breakdown"]["passing_interception_points"] == -2.0


def test_rushing_100_yard_bonus():
    below = calculate_actual_offense_dk_points(_row(rushing_yards=99))
    at = calculate_actual_offense_dk_points(_row(rushing_yards=100))
    assert below["breakdown"]["rushing_100_bonus_points"] == 0.0
    assert at["breakdown"]["rushing_100_bonus_points"] == 3.0


def test_reception_scoring_is_full_ppr():
    result = calculate_actual_offense_dk_points(_row(position="WR", receptions=7, receiving_yards=80))
    assert result["breakdown"]["reception_points"] == 7.0
    assert result["breakdown"]["receiving_yard_points"] == 8.0


def test_receiving_100_yard_bonus():
    at = calculate_actual_offense_dk_points(_row(position="WR", receiving_yards=100))
    assert at["breakdown"]["receiving_100_bonus_points"] == 3.0


def test_fumble_lost_penalty():
    result = calculate_actual_offense_dk_points(_row(fumbles_lost_total=1))
    assert result["breakdown"]["fumble_lost_points"] == -1.0


def test_two_point_conversion_summed_across_all_three_types():
    result = calculate_actual_offense_dk_points(_row(rushing_2pt_conversions=1, receiving_2pt_conversions=1))
    assert result["breakdown"]["two_point_conversion_points"] == 4.0


def test_all_offense_touchdowns_are_six_points_except_passing():
    rush = calculate_actual_offense_dk_points(_row(rushing_tds=1))
    rec = calculate_actual_offense_dk_points(_row(position="WR", receiving_tds=1))
    pas = calculate_actual_offense_dk_points(_row(passing_tds=1))
    assert rush["breakdown"]["rushing_td_points"] == 6.0
    assert rec["breakdown"]["receiving_td_points"] == 6.0
    assert pas["breakdown"]["passing_td_points"] == 4.0


def test_points_allowed_brackets_exact_thresholds():
    assert points_allowed_bonus(0) == 10.0
    assert points_allowed_bonus(6) == 7.0
    assert points_allowed_bonus(7) == 4.0
    assert points_allowed_bonus(13) == 4.0
    assert points_allowed_bonus(14) == 1.0
    assert points_allowed_bonus(21) == 0.0
    assert points_allowed_bonus(27) == 0.0
    assert points_allowed_bonus(28) == -1.0
    assert points_allowed_bonus(35) == -4.0
    assert points_allowed_bonus(50) == -4.0


def test_dst_not_scored_when_team_stats_missing():
    result = calculate_actual_dst_dk_points("PHI", None, [], 20)
    assert result["scored"] is False


def test_dst_not_scored_when_points_allowed_missing():
    result = calculate_actual_dst_dk_points("PHI", {"def_sacks": 1.0}, [], None)
    assert result["scored"] is False


def test_dst_scoring_components():
    team_stats = {
        "def_sacks": 3.0, "def_interceptions": 1, "def_safeties": 0,
        "def_fg_blocks": 0, "def_pat_blocks": 0, "def_punt_blocks": 1,
        "def_tds": 1, "special_teams_tds": 0,
    }
    result = calculate_actual_dst_dk_points("PHI", team_stats, [], points_allowed=13)
    assert result["breakdown"]["sack_points"] == 3.0
    assert result["breakdown"]["interception_points"] == 2.0
    assert result["breakdown"]["blocked_kick_points"] == 2.0
    assert result["breakdown"]["defensive_or_return_td_points"] == 6.0
    assert result["breakdown"]["points_allowed_bonus_points"] == 4.0


def test_dst_fumble_recovery_derived_from_pbp_never_own_fumble():
    pbp = [
        {"fumble_recovery_1_team": "PHI", "posteam": "DAL"},  # real takeaway
        {"fumble_recovery_1_team": "PHI", "posteam": "PHI"},  # own fumble recovery -- not a takeaway
        {"fumble_recovery_1_team": "DAL", "posteam": "PHI"},  # opponent's takeaway, not PHI's
    ]
    result = calculate_actual_dst_dk_points("PHI", {"def_sacks": 0.0}, pbp, points_allowed=21)
    assert result["breakdown"]["fumble_recovery_points"] == 2.0  # exactly one real takeaway
