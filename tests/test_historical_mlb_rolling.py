"""Milestone 32.0 -- historical_mlb/rolling.py. No network calls."""

from historical_mlb.rolling import (
    aggregate_statcast_rates,
    build_rolling_hitter_stats,
    build_rolling_pitcher_stats,
)

HITTER_LOG = [
    {"date": "2025-06-01", "stat": {"plateAppearances": 4, "atBats": 4, "hits": 2, "doubles": 1, "triples": 0, "homeRuns": 0, "baseOnBalls": 0, "hitByPitch": 0, "sacFlies": 0, "strikeOuts": 1, "stolenBases": 0}},
    {"date": "2025-06-10", "stat": {"plateAppearances": 5, "atBats": 4, "hits": 2, "doubles": 0, "triples": 0, "homeRuns": 1, "baseOnBalls": 1, "hitByPitch": 0, "sacFlies": 0, "strikeOuts": 0, "stolenBases": 1}},
    # This one is ON the target date -- must be excluded (it's the target game's own result).
    {"date": "2025-06-15", "stat": {"plateAppearances": 5, "atBats": 5, "hits": 5, "doubles": 0, "triples": 0, "homeRuns": 3, "baseOnBalls": 0, "hitByPitch": 0, "sacFlies": 0, "strikeOuts": 0, "stolenBases": 0}},
    # Far in the past -- outside a 14-day window but inside season-to-date.
    {"date": "2025-04-01", "stat": {"plateAppearances": 4, "atBats": 4, "hits": 0, "doubles": 0, "triples": 0, "homeRuns": 0, "baseOnBalls": 0, "hitByPitch": 0, "sacFlies": 0, "strikeOuts": 3, "stolenBases": 0}},
]


def test_rolling_hitter_excludes_target_game_itself():
    stats = build_rolling_hitter_stats(HITTER_LOG, target_game_date="2025-06-15", window_days=None, window_label="season_to_date")
    assert stats.games == 3  # not 4 -- the 2025-06-15 entry (the target game) is excluded
    assert stats.home_runs == 1  # only the 06-01/06-10/04-01 entries' home runs (0+1+0)


def test_rolling_hitter_respects_window_days():
    stats_14d = build_rolling_hitter_stats(HITTER_LOG, target_game_date="2025-06-15", window_days=14, window_label="last_14d")
    # 06-01 is 14 days before 06-15 (included), 06-10 is 5 days before (included), 04-01 is far outside.
    assert stats_14d.games == 2


def test_rolling_hitter_computed_rates():
    stats = build_rolling_hitter_stats(HITTER_LOG[:2], target_game_date="2025-06-15", window_days=None, window_label="season_to_date")
    assert stats.ab == 8
    assert stats.hits == 4
    assert stats.avg == 0.5
    assert stats.home_runs == 1
    assert stats.doubles == 1


def test_rolling_hitter_zero_games_returns_none_rates_not_crash():
    stats = build_rolling_hitter_stats([], target_game_date="2025-06-15", window_days=7, window_label="last_7d")
    assert stats.games == 0
    assert stats.avg is None
    assert stats.woba_proxy is None


PITCHER_LOG = [
    {"date": "2025-06-05", "stat": {"inningsPitched": "6.2", "battersFaced": 26, "strikeOuts": 7, "baseOnBalls": 2, "hits": 4, "earnedRuns": 1, "homeRuns": 0}},
    {"date": "2025-06-15", "stat": {"inningsPitched": "7.0", "battersFaced": 28, "strikeOuts": 9, "baseOnBalls": 0, "hits": 2, "earnedRuns": 0, "homeRuns": 0}},
]


def test_rolling_pitcher_excludes_target_game_and_computes_era():
    stats = build_rolling_pitcher_stats(PITCHER_LOG, target_game_date="2025-06-15", window_days=None, window_label="season_to_date")
    assert stats.games == 1
    assert stats.outs == 20  # "6.2" == 20 outs, from the non-target entry only
    assert stats.era == round((1 * 9) / (20 / 3), 2)


def test_rolling_pitcher_innings_notation_not_misparsed_as_decimal():
    stats = build_rolling_pitcher_stats(PITCHER_LOG[:1], target_game_date="2025-07-01", window_days=None, window_label="season_to_date")
    assert stats.outs == 20  # not 6.2*3=18.6 or any decimal-notation error


def test_aggregate_statcast_rates_computes_hard_hit_and_barrel_proxy():
    rows = [
        {"batter": "592450", "launch_speed": "96.0", "launch_angle": "10"},   # hard hit, not a barrel
        {"batter": "592450", "launch_speed": "99.0", "launch_angle": "28", "estimated_woba_using_speedangle": "1.800"},  # hard hit + barrel
        {"batter": "592450", "launch_speed": "70.0", "launch_angle": "5"},    # neither
        {"batter": "999999", "launch_speed": "99.0", "launch_angle": "28"},   # different player, ignored
    ]
    result = aggregate_statcast_rates(rows, "batter", "592450")
    assert result["batted_ball_events"] == 3
    assert result["hard_hit_rate"] == round(2 / 3, 4)
    assert result["barrel_rate_proxy"] == round(1 / 3, 4)
    assert result["avg_xwoba_contribution"] == 1.8


def test_aggregate_statcast_rates_no_events_returns_none_not_crash():
    result = aggregate_statcast_rates([], "batter", "592450")
    assert result["batted_ball_events"] == 0
    assert result["hard_hit_rate"] is None
