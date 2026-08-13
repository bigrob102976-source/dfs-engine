import pytest

from evaluation.dk_actual_scoring import calculate_actual_dk_points
from evaluation.results_enrichment import ActualPitcherResult

RETRIEVED_AT = "2026-08-06T12:00:00+00:00"


def _result(status="completed_start", **overrides):
    base = dict(
        player_id="1", game_id="111", game_date="2026-08-05", status=status,
        outs=18, batters_faced=23, strikeouts=8, walks=2, hits_allowed=3,
        earned_runs=3, home_runs_allowed=1, hit_batsmen=0, pitch_count=93,
        win=False, loss=False, complete_game=False, shutout=False, no_hitter=False,
        retrieved_at=RETRIEVED_AT,
    )
    base.update(overrides)
    return ActualPitcherResult(**base)


def test_reuses_centralized_dk_scoring_config():
    from config import scoring_config
    scoring = calculate_actual_dk_points(_result())
    # Recompute independently from the SAME config dict to prove no
    # duplicated/hardcoded point values exist in the actual-scoring path.
    dk = scoring_config.DK_SCORING
    expected = round(
        (18 / 3.0) * dk["innings_pitched"] + 8 * dk["strikeout"] + 3 * dk["earned_run"]
        + 2 * dk["walk"] + 3 * dk["hit_against"], 2
    )
    assert scoring["dfs_points"] == expected


def test_basic_completed_start_scoring_matches_hand_calculation():
    # 6.0 IP (18 outs), 8 K, 2 BB, 3 H, 3 ER, no decision, no CG.
    # 6.0*2.25 + 8*2.0 - 3*2.0 - 2*0.6 - 3*0.6 = 13.5+16-6-1.2-1.8 = 20.5
    scoring = calculate_actual_dk_points(_result())
    assert scoring["scored"] is True
    assert scoring["dfs_points"] == 20.5


def test_win_bonus_applied():
    with_win = calculate_actual_dk_points(_result(win=True))
    without_win = calculate_actual_dk_points(_result(win=False))
    assert with_win["dfs_points"] - without_win["dfs_points"] == 4.0


def test_complete_game_shutout_no_hitter_bonuses_stack():
    cg_only = calculate_actual_dk_points(_result(complete_game=True, hits_allowed=3))
    cg_shutout = calculate_actual_dk_points(_result(complete_game=True, shutout=True, hits_allowed=3))
    cg_shutout_no_hitter = calculate_actual_dk_points(_result(complete_game=True, shutout=True, no_hitter=True, hits_allowed=0))

    plain = calculate_actual_dk_points(_result(hits_allowed=3))
    assert cg_only["dfs_points"] - plain["dfs_points"] == pytest.approx(2.5)
    assert cg_shutout["dfs_points"] - cg_only["dfs_points"] == pytest.approx(2.5)
    # no_hitter case also removes the 3 hits' -0.6*3 penalty vs the others, so
    # compare its bonus breakdown directly instead of the total.
    assert cg_shutout_no_hitter["breakdown"]["complete_game_bonus_points"] == pytest.approx(2.5 + 2.5 + 5.0)


def test_hit_batsman_penalty_applied():
    scoring = calculate_actual_dk_points(_result(hit_batsmen=2))
    assert scoring["breakdown"]["hit_batsman_points"] == pytest.approx(-1.2)


def test_scratched_pitcher_is_not_scored():
    scoring = calculate_actual_dk_points(_result(status="scratched", outs=None, strikeouts=None))
    assert scoring["scored"] is False
    assert scoring["dfs_points"] is None
    assert scoring["breakdown"] == {}


def test_postponed_pitcher_is_not_scored():
    scoring = calculate_actual_dk_points(_result(status="postponed", outs=None))
    assert scoring["scored"] is False


def test_did_not_start_pitcher_is_still_scored():
    # An opener/piggyback appearance still racked up real DK points.
    scoring = calculate_actual_dk_points(_result(status="did_not_start", outs=9, strikeouts=2, walks=0, hits_allowed=1, earned_runs=0))
    assert scoring["scored"] is True
    assert scoring["dfs_points"] is not None


def test_zero_ip_does_not_crash_and_scores_only_batters_faced_events():
    scoring = calculate_actual_dk_points(_result(outs=0, strikeouts=0, walks=0, hits_allowed=1, earned_runs=1, home_runs_allowed=1))
    assert scoring["scored"] is True
    assert scoring["breakdown"]["innings_points"] == 0.0


def test_missing_dk_scoring_key_defaults_to_zero_not_a_crash():
    # A minimal DK_SCORING config missing the optional bonus keys entirely
    # must not raise -- see config/scoring_config.py's "skip absent bonus" note.
    minimal = {"innings_pitched": 2.25, "strikeout": 2.0, "earned_run": -2.0, "walk": -0.6, "hit_against": -0.6}
    scoring = calculate_actual_dk_points(_result(win=True, hit_batsmen=1), dk_scoring=minimal)
    assert scoring["scored"] is True
    assert scoring["breakdown"]["win_points"] == 0.0
    assert scoring["breakdown"]["hit_batsman_points"] == 0.0
