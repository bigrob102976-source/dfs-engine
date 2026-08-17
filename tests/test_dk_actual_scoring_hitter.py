from evaluation.dk_actual_scoring import calculate_actual_hitter_dk_points
from evaluation.hitter_results_enrichment import ActualHitterResult

RETRIEVED_AT = "2026-08-06T12:00:00+00:00"


def _result(status="appeared", **overrides):
    base = dict(
        player_id="1", game_id="111", game_date="2026-08-05", status=status,
        plate_appearances=5, at_bats=4, runs=1, hits=2, doubles=1, triples=0,
        home_runs=1, rbi=3, walks=1, strikeouts=1, hit_by_pitch=0, stolen_bases=0,
        retrieved_at=RETRIEVED_AT,
    )
    base.update(overrides)
    return ActualHitterResult(**base)


def test_reuses_centralized_dk_hitter_scoring_config():
    from config import batter_scoring_config

    scoring = calculate_actual_hitter_dk_points(_result())
    dk = batter_scoring_config.DK_HITTER_SCORING
    # 2 hits - 1 double - 0 triple - 1 HR = 0 singles
    expected = round(
        0 * dk["single"] + 1 * dk["double"] + 1 * dk["home_run"] + 3 * dk["rbi"]
        + 1 * dk["run"] + 1 * dk["walk"], 2
    )
    assert scoring["dfs_points"] == expected


def test_basic_appeared_scoring_matches_hand_calculation():
    # 0 singles, 1 double, 1 HR, 3 RBI, 1 run, 1 BB.
    # 0*3 + 1*5 + 1*10 + 3*2 + 1*2 + 1*2 = 5+10+6+2+2 = 25
    scoring = calculate_actual_hitter_dk_points(_result())
    assert scoring["scored"] is True
    assert scoring["dfs_points"] == 25.0


def test_singles_derived_from_hits_minus_extra_base_hits():
    scoring = calculate_actual_hitter_dk_points(_result(hits=4, doubles=1, triples=0, home_runs=0))
    assert scoring["breakdown"]["single_points"] == 9.0  # 3 singles * 3.0


def test_stolen_base_and_hbp_scored():
    scoring = calculate_actual_hitter_dk_points(_result(stolen_bases=2, hit_by_pitch=1))
    assert scoring["breakdown"]["stolen_base_points"] == 10.0
    assert scoring["breakdown"]["hit_by_pitch_points"] == 2.0


def test_scratched_hitter_is_not_scored():
    scoring = calculate_actual_hitter_dk_points(_result(status="scratched", hits=None))
    assert scoring["scored"] is False
    assert scoring["dfs_points"] is None
    assert scoring["breakdown"] == {}


def test_postponed_hitter_is_not_scored():
    scoring = calculate_actual_hitter_dk_points(_result(status="postponed", hits=None))
    assert scoring["scored"] is False


def test_zero_stats_does_not_crash():
    scoring = calculate_actual_hitter_dk_points(_result(hits=0, doubles=0, triples=0, home_runs=0, rbi=0, runs=0, walks=0, hit_by_pitch=0, stolen_bases=0))
    assert scoring["scored"] is True
    assert scoring["dfs_points"] == 0.0


def test_missing_dk_scoring_key_raises_no_crash_with_full_dict():
    minimal = {"single": 3.0, "double": 5.0, "triple": 8.0, "home_run": 10.0, "rbi": 2.0, "run": 2.0, "walk": 2.0, "hit_by_pitch": 2.0, "stolen_base": 5.0}
    scoring = calculate_actual_hitter_dk_points(_result(), dk_scoring=minimal)
    assert scoring["scored"] is True
