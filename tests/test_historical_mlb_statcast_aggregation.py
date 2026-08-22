"""Milestone 32.1, Parts 16/18 -- statcast_aggregation.py. No network calls."""

from historical_mlb.statcast_aggregation import (
    hitter_platoon_splits,
    opponent_offense_aggregate,
    pitcher_platoon_splits_allowed,
)


def _pitch(batter="592450", pitcher="543135", events=None, p_throws="R", stand="R", home_team="NYY", away_team="BOS", topbot="Top", game_pk=1):
    return {
        "batter": batter, "pitcher": pitcher, "events": events or "", "p_throws": p_throws, "stand": stand,
        "home_team": home_team, "away_team": away_team, "inning_topbot": topbot, "game_pk": game_pk,
    }


def test_hitter_platoon_splits_separates_by_pitcher_hand():
    rows = [
        _pitch(events="single", p_throws="L"),
        _pitch(events="strikeout", p_throws="L"),
        _pitch(events="home_run", p_throws="R"),
        _pitch(events="", p_throws="R"),  # not a PA-ending pitch -- excluded
    ]
    result = hitter_platoon_splits(rows, "592450")
    assert result["vs_lhp"]["pa"] == 2
    assert result["vs_rhp"]["pa"] == 1
    assert result["vs_rhp"]["avg"] == 1.0  # 1-for-1 with a HR


def test_hitter_platoon_splits_ignores_other_batters():
    rows = [_pitch(batter="999999", events="single", p_throws="L")]
    result = hitter_platoon_splits(rows, "592450")
    assert result["vs_lhp"]["pa"] == 0


def test_pitcher_platoon_splits_allowed_separates_by_batter_stand():
    rows = [
        _pitch(events="single", stand="L"),
        _pitch(events="walk", stand="R"),
    ]
    result = pitcher_platoon_splits_allowed(rows, "543135")
    assert result["vs_lhb"]["pa"] == 1
    assert result["vs_rhb"]["pa"] == 1
    assert result["vs_rhb"]["obp"] == 1.0  # a walk is a PA and reaches base


def test_pa_stat_line_computes_avg_obp_slg_correctly():
    rows = [
        _pitch(events="single", stand="L"), _pitch(events="double", stand="L"),
        _pitch(events="strikeout", stand="L"), _pitch(events="walk", stand="L"),
    ]
    result = pitcher_platoon_splits_allowed(rows, "543135")
    line = result["vs_lhb"]
    assert line["pa"] == 4
    # ab = pa - bb - hbp - sacfly = 4 - 1 = 3; hits = 2 (1B + 2B); avg = 2/3
    assert line["avg"] == round(2 / 3, 4)
    # total bases = 1 + 2 = 3; slg = 3/3 = 1.0
    assert line["slg"] == 1.0


def test_opponent_offense_aggregate_uses_batting_team_from_inning_topbot():
    # Top of the inning -> away team batting; Bot -> home team batting.
    rows = [
        _pitch(events="single", home_team="NYY", away_team="BOS", topbot="Top"),  # BOS batting
        _pitch(events="strikeout", home_team="NYY", away_team="BOS", topbot="Bot"),  # NYY batting
    ]
    bos_offense = opponent_offense_aggregate(rows, "BOS")
    assert bos_offense["sample_pa"] == 1
    nyy_offense = opponent_offense_aggregate(rows, "NYY")
    assert nyy_offense["sample_pa"] == 1
    assert nyy_offense["k_pct"] == 1.0


def test_opponent_offense_aggregate_zero_sample_returns_none_not_crash():
    result = opponent_offense_aggregate([], "BOS")
    assert result["sample_pa"] == 0
    assert result["k_pct"] is None


def test_opponent_offense_aggregate_counts_distinct_sample_games():
    rows = [
        _pitch(events="single", away_team="BOS", topbot="Top", game_pk=1),
        _pitch(events="single", away_team="BOS", topbot="Top", game_pk=2),
    ]
    result = opponent_offense_aggregate(rows, "BOS")
    assert result["sample_games"] == 2
