from config import batter_scoring_config as batter_cfg
from config import scoring_config as pitcher_cfg
from fantasypros.scoring import calculate_fantasypros_hitter_dk_points, calculate_fantasypros_pitcher_dk_points


def test_hitter_dk_points_uses_exact_dk_hitter_scoring_weights():
    stats = {"1b": 1.0, "2b": 1.0, "3b": 1.0, "hrs": 1.0, "rbi": 1.0, "runs": 1.0, "bb": 1.0, "hbp": 1.0, "sb": 1.0}
    result = calculate_fantasypros_hitter_dk_points(stats)
    dk = batter_cfg.DK_HITTER_SCORING
    expected = dk["single"] + dk["double"] + dk["triple"] + dk["home_run"] + dk["rbi"] + dk["run"] + dk["walk"] + dk["hit_by_pitch"] + dk["stolen_base"]
    assert result["dk_points"] == round(expected, 2)


def test_hitter_dk_points_freddie_freeman_sample():
    # Real FantasyPros sample (2026-08-19 live probe).
    stats = {"1b": 1.06, "2b": 0.39, "3b": 0, "hrs": 0.09, "rbi": 0.45, "runs": 0.61, "bb": 0.28, "hbp": 0.05, "sb": 0.04}
    result = calculate_fantasypros_hitter_dk_points(stats)
    dk = batter_cfg.DK_HITTER_SCORING
    expected = (
        1.06 * dk["single"] + 0.39 * dk["double"] + 0 * dk["triple"] + 0.09 * dk["home_run"]
        + 0.45 * dk["rbi"] + 0.61 * dk["run"] + 0.28 * dk["walk"] + 0.05 * dk["hit_by_pitch"] + 0.04 * dk["stolen_base"]
    )
    assert result["dk_points"] == round(expected, 2)


def test_hitter_dk_points_never_uses_ibb_double_counting_bb():
    """FantasyPros' "bb" already includes intentional walks -- "ibb" must
    never be added on top, which would double-count."""
    with_ibb = {"bb": 1.0, "ibb": 1.0}
    without_ibb_field = {"bb": 1.0}
    assert calculate_fantasypros_hitter_dk_points(with_ibb)["dk_points"] == calculate_fantasypros_hitter_dk_points(without_ibb_field)["dk_points"]


def test_hitter_dk_points_missing_fields_contribute_zero_not_invented():
    result = calculate_fantasypros_hitter_dk_points({})
    assert result["dk_points"] == 0.0
    assert all(v == 0.0 for v in result["breakdown"].values())


def test_pitcher_dk_points_uses_exact_dk_scoring_weights():
    stats = {"ip": 1.0, "k": 1.0, "er": 1.0, "bbi": 1.0, "h": 1.0, "hp": 1.0, "w": 1.0, "cg": 1.0, "sho": 1.0}
    result = calculate_fantasypros_pitcher_dk_points(stats)
    dk = pitcher_cfg.DK_SCORING
    expected = (
        dk["innings_pitched"] + dk["strikeout"] + dk["earned_run"] + dk["walk"] + dk["hit_against"]
        + dk["hit_batsman"] + dk["win"] + dk["complete_game"] + dk["complete_game_shutout"]
    )
    assert result["dk_points"] == round(expected, 2)


def test_pitcher_dk_points_chapman_sample():
    stats = {"ip": 0.39, "k": 0.49, "er": 0.14, "bbi": 0.18, "h": 0.29, "hp": 0.01, "w": 0.03, "cg": 0, "sho": 0}
    result = calculate_fantasypros_pitcher_dk_points(stats)
    dk = pitcher_cfg.DK_SCORING
    expected = (
        0.39 * dk["innings_pitched"] + 0.49 * dk["strikeout"] + 0.14 * dk["earned_run"] + 0.18 * dk["walk"]
        + 0.29 * dk["hit_against"] + 0.01 * dk["hit_batsman"] + 0.03 * dk["win"]
    )
    assert result["dk_points"] == round(expected, 2)


def test_pitcher_dk_points_walk_uses_bbi_not_hitter_bb():
    """Pitcher walks-issued ("bbi") must be read, never the unrelated
    hitter-side "bb" field (which doesn't exist on a pitcher record, but
    a wrong key name would silently score 0 instead of a real penalty)."""
    result = calculate_fantasypros_pitcher_dk_points({"bbi": 2.0})
    dk = pitcher_cfg.DK_SCORING
    assert result["dk_points"] == round(2.0 * dk["walk"], 2)


def test_pitcher_dk_points_missing_fields_contribute_zero_not_invented():
    result = calculate_fantasypros_pitcher_dk_points({})
    assert result["dk_points"] == 0.0
    assert all(v == 0.0 for v in result["breakdown"].values())


def test_pitcher_dk_points_negative_for_a_bad_projected_line():
    """A pitcher projected to allow a lot of earned runs/hits should be
    able to score negative -- DK's own earned_run/hit_against weights are
    negative, and this must not be clamped to 0."""
    stats = {"ip": 1.0, "er": 5.0, "h": 8.0}
    result = calculate_fantasypros_pitcher_dk_points(stats)
    assert result["dk_points"] < 0
