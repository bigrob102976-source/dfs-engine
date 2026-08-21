"""Milestone 32.0 -- historical_mlb/scoring.py. No network calls; fixed
DK_SCORING/DK_HITTER_SCORING values are hand-verified against this
project's real config (config/scoring_config.py, config/batter_scoring_config.py)
in the comments below so a future scoring-weight change makes these
assertions fail loudly rather than silently drifting."""

from historical_mlb.scoring import (
    hitter_result_from_boxscore_entry,
    pitcher_result_from_boxscore_entry,
    score_boxscore,
)


def _pitcher_entry(**stat_overrides):
    stat = {
        "inningsPitched": "6.2", "strikeOuts": 7, "baseOnBalls": 2, "hits": 4,
        "earnedRuns": 1, "homeRuns": 0, "hitBatsmen": 0, "battersFaced": 26,
        "wins": True, "losses": False, "completeGames": False, "shutouts": False,
    }
    stat.update(stat_overrides)
    return {"player_id": "543135", "name": "Test Pitcher", "team": "NYY", "side": "home", "stat": stat}


def _hitter_entry(**stat_overrides):
    stat = {
        "plateAppearances": 4, "atBats": 3, "runs": 1, "hits": 2, "doubles": 0, "triples": 0,
        "homeRuns": 1, "rbi": 2, "baseOnBalls": 1, "strikeOuts": 0, "hitByPitch": 0, "stolenBases": 0,
    }
    stat.update(stat_overrides)
    return {"player_id": "592450", "name": "Test Hitter", "team": "NYY", "side": "home", "stat": stat}


def test_pitcher_innings_notation_parsed_correctly_not_as_decimal():
    result = pitcher_result_from_boxscore_entry(_pitcher_entry(), game_id="1", game_date="2025-06-15")
    assert result.outs == 20  # "6.2" == 6 innings + 2 outs == 20 outs, NOT 6.2*3


def test_pitcher_dk_points_matches_hand_computed_total():
    # innings: 20 outs -> 6.6667 IP * 2.25 = 15.0
    # strikeouts: 7 * 2.0 = 14.0
    # earned_run: 1 * -2.0 = -2.0
    # walks: 2 * -0.6 = -1.2
    # hits: 4 * -0.6 = -2.4
    # win: 4.0
    # total = 15.0 + 14.0 - 2.0 - 1.2 - 2.4 + 4.0 = 27.4
    pitchers, _ = score_boxscore([_pitcher_entry()], [], game_id="1", game_date="2025-06-15")
    assert pitchers[0]["actual_dk_points"] == 27.4


def test_pitcher_zero_home_runs_allowed_is_zero_not_none():
    result = pitcher_result_from_boxscore_entry(_pitcher_entry(homeRuns=0), game_id="1", game_date="2025-06-15")
    assert result.home_runs_allowed == 0  # regression guard: must not collapse a real 0 into None


def test_hitter_dk_points_matches_hand_computed_total():
    # hits=2, HR=1 -> singles=1: 1*3.0=3.0; HR: 1*10.0=10.0; rbi: 2*2.0=4.0
    # run: 1*2.0=2.0; walk: 1*2.0=2.0 -> total = 21.0
    _, hitters = score_boxscore([], [_hitter_entry()], game_id="1", game_date="2025-06-15")
    assert hitters[0]["actual_dk_points"] == 21.0
    assert hitters[0]["actual_1b"] == 1
    assert hitters[0]["actual_hr"] == 1


def test_hitter_zero_plate_appearances_is_zero_not_none():
    # A defensive replacement / pinch runner who appeared but never batted.
    result = hitter_result_from_boxscore_entry(_hitter_entry(plateAppearances=0, atBats=0, hits=0, homeRuns=0, rbi=0, runs=0, baseOnBalls=0), game_id="1", game_date="2025-06-15")
    assert result.plate_appearances == 0  # regression guard: must not collapse a real 0 into None


def test_score_boxscore_breakdown_is_auditable_not_just_a_bare_number():
    pitchers, _ = score_boxscore([_pitcher_entry()], [], game_id="1", game_date="2025-06-15")
    breakdown = pitchers[0]["dk_points_breakdown"]
    assert breakdown["strikeout_points"] == 14.0
    assert breakdown["win_points"] == 4.0
    assert round(sum(breakdown.values()), 2) == pitchers[0]["actual_dk_points"]
