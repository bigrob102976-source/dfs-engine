import pytest

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS, DK_ROSTER_SIZE
from config.ownership_config import OWNERSHIP_MODEL_VERSION
from ownership.model import build_ownership_projections
from tests._ownership_fixtures import hitter, pitcher, small_slate_hitters, small_slate_pitchers


def _pitcher_slot_count():
    return next(s["count"] for s in DK_CLASSIC_ROSTER_SLOTS if s["slot"] == "P")


def test_pitcher_ownership_sums_to_expected_total():
    pitchers = small_slate_pitchers()
    hitters = small_slate_hitters()
    projections, _team_pop, report = build_ownership_projections(pitchers, hitters, 1.0)
    expected = _pitcher_slot_count() * 100.0
    pitcher_sum = sum(p.projected_ownership for p in projections if p.player_type == "pitcher")
    assert pitcher_sum == pytest.approx(expected, abs=0.5)
    assert report["pitcher_ownership_sum"] == pytest.approx(expected, abs=0.5)


def test_hitter_ownership_sums_to_expected_total():
    pitchers = small_slate_pitchers()
    hitters = small_slate_hitters()
    projections, _team_pop, report = build_ownership_projections(pitchers, hitters, 1.0)
    expected = (DK_ROSTER_SIZE - _pitcher_slot_count()) * 100.0
    hitter_sum = sum(h.projected_ownership for h in projections if h.player_type == "hitter")
    assert hitter_sum == pytest.approx(expected, abs=0.5)
    assert report["hitter_ownership_expected"] == expected


def test_no_projected_ownership_below_zero():
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    assert all(p.projected_ownership >= 0.0 for p in projections)


def test_no_projected_ownership_above_100():
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    assert all(p.projected_ownership <= 100.0 for p in projections)


def test_dominant_pitcher_gets_capped_not_over_100():
    dominant = pitcher("dominant", "TOR", 12000, 40.0, overall=99.0, tags=["elite_k_upside"])
    others = [pitcher(f"p{i}", f"T{i}", 4000, 5.0, overall=20.0) for i in range(5)]
    projections, _t, report = build_ownership_projections([dominant] + others, [], 1.0)
    dom = [p for p in projections if p.dk_player_id == "dominant"][0]
    assert dom.projected_ownership <= 100.0
    assert report["players_above_100"] == 0


def test_deterministic_across_repeated_calls():
    pitchers = small_slate_pitchers()
    hitters = small_slate_hitters()
    first, _t1, _r1 = build_ownership_projections(pitchers, hitters, 1.0)
    second, _t2, _r2 = build_ownership_projections(pitchers, hitters, 1.0)
    first_map = {p.dk_player_id: p.projected_ownership for p in first}
    second_map = {p.dk_player_id: p.projected_ownership for p in second}
    assert first_map == second_map


def test_chalk_score_in_range():
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    assert all(0.0 <= p.chalk_score <= 100.0 for p in projections)


def test_ownership_tier_is_one_of_configured_names():
    from config.ownership_config import OWNERSHIP_TIER_THRESHOLDS
    valid = {name for name, _lo, _hi in OWNERSHIP_TIER_THRESHOLDS}
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    assert all(p.ownership_tier in valid for p in projections)


def test_ownership_confidence_in_range():
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    assert all(0.0 <= p.ownership_confidence <= 100.0 for p in projections)


def test_model_version_tagged_on_every_projection():
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    assert all(p.model_version == OWNERSHIP_MODEL_VERSION for p in projections)


def test_small_sample_hitter_does_not_reach_35_percent_ownership():
    # Mirrors the milestone's explicit example: 4 PA with an extreme
    # projection should not automatically project heavy ownership.
    tiny = hitter("tiny", "AAA", ["OF"], 2000, 20.0, order=9, pa=4, overall=95.0)
    hitters = small_slate_hitters() + [tiny]
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), hitters, 1.0)
    tiny_result = [p for p in projections if p.dk_player_id == "tiny"][0]
    assert tiny_result.projected_ownership < 35.0


def test_small_sample_hitter_owns_less_than_if_it_had_full_sample():
    tiny = hitter("tiny", "AAA", ["OF"], 2000, 20.0, order=9, pa=4, overall=95.0)
    full = hitter("full", "AAA", ["OF"], 2000, 20.0, order=9, pa=400, overall=95.0)
    base_hitters = small_slate_hitters()

    proj_tiny, _t1, _r1 = build_ownership_projections(small_slate_pitchers(), base_hitters + [tiny], 1.0)
    proj_full, _t2, _r2 = build_ownership_projections(small_slate_pitchers(), base_hitters + [full], 1.0)

    tiny_own = [p for p in proj_tiny if p.dk_player_id == "tiny"][0].projected_ownership
    full_own = [p for p in proj_full if p.dk_player_id == "full"][0].projected_ownership
    assert tiny_own < full_own


def test_reasons_are_nonempty_and_capped():
    projections, _t, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    assert all(1 <= len(p.reasons) <= 6 for p in projections)


def test_team_popularity_aggregate_ownership_matches_sum_of_its_hitters():
    projections, team_pop, _r = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), 1.0)
    for team, stats in team_pop.items():
        expected = sum(p.projected_ownership for p in projections if p.team == team and p.player_type == "hitter")
        assert stats.aggregate_projected_ownership == pytest.approx(expected, abs=0.01)


def test_empty_pool_does_not_crash():
    projections, team_pop, report = build_ownership_projections([], [], 1.0)
    assert projections == []
    assert team_pop == {}
    assert report["pitcher_ownership_sum"] == 0.0
    assert report["hitter_ownership_sum"] == 0.0
