import pytest

from ownership.features import (
    build_hitter_features,
    build_pitcher_features,
    compute_team_popularity,
    sample_size_dampening,
)
from tests._ownership_fixtures import hitter, pitcher, small_slate_hitters, small_slate_pitchers


def test_pitcher_projection_percentile_best_is_100():
    pitchers = small_slate_pitchers()
    team_pop = {}
    features = build_pitcher_features(pitchers, team_pop)
    assert features["p1"]["projection_percentile"] == 100.0  # highest projection (22.0)


def test_pitcher_salary_percentile_highest_salary_is_100():
    pitchers = small_slate_pitchers()
    features = build_pitcher_features(pitchers, {})
    assert features["p1"]["salary_percentile"] == 100.0  # highest salary (8500)


def test_pitcher_value_percentile_computed():
    pitchers = small_slate_pitchers()
    features = build_pitcher_features(pitchers, {})
    for f in features.values():
        assert 0.0 <= f["value_percentile"] <= 100.0


def test_pitcher_k_upside_from_tag():
    pitchers = small_slate_pitchers()
    features = build_pitcher_features(pitchers, {})
    assert features["p1"]["k_upside"] == 100.0  # has elite_k_upside tag
    assert features["p2"]["k_upside"] < 100.0  # no tag


def test_pitcher_opponent_weakness_uses_team_popularity():
    pitchers = [pitcher("p1", "TOR", 7000, 18.0, opponent="WEAK"), pitcher("p2", "PIT", 7000, 18.0, opponent="STRONG")]
    from ownership.models import TeamPopularity
    team_pop = {
        "WEAK": TeamPopularity(team="WEAK", team_popularity_score=10.0, aggregate_projection=0, top5_projection=0, hitter_count=5),
        "STRONG": TeamPopularity(team="STRONG", team_popularity_score=90.0, aggregate_projection=0, top5_projection=0, hitter_count=5),
    }
    features = build_pitcher_features(pitchers, team_pop)
    # facing a weak offense (low team_popularity_score) -> high opponent_weakness_percentile
    assert features["p1"]["opponent_weakness_percentile"] > features["p2"]["opponent_weakness_percentile"]


def test_pitcher_salary_savings_rewards_cheap_comparable_projection():
    # p_cheap and p_expensive project similarly; p_cheap should show
    # higher salary-savings than p_expensive.
    pitchers = [
        pitcher("p_cheap", "TOR", 5000, 18.0),
        pitcher("p_expensive", "PIT", 9000, 18.2),
        pitcher("p_other", "ATL", 7000, 10.0),
    ]
    features = build_pitcher_features(pitchers, {})
    assert features["p_cheap"]["salary_savings_percentile"] > features["p_expensive"]["salary_savings_percentile"]


def test_hitter_position_scarcity_higher_when_few_alternatives():
    # Only one 'SS' overall (max scarcity possible for a solo position)
    # vs. six OF alternatives (saturated, minimum scarcity).
    hitters = [
        hitter("only_ss", "AAA", ["SS"], 4000, 8.0),
        hitter("of1", "AAA", ["OF"], 4000, 8.0),
        hitter("of2", "BBB", ["OF"], 4000, 8.0),
        hitter("of3", "CCC", ["OF"], 4000, 8.0),
        hitter("of4", "DDD", ["OF"], 4000, 8.0),
        hitter("of5", "EEE", ["OF"], 4000, 8.0),
        hitter("of6", "FFF", ["OF"], 4000, 8.0),
    ]
    features = build_hitter_features(hitters, {})
    assert features["only_ss"]["position_scarcity"] > features["of1"]["position_scarcity"]
    assert features["of1"]["position_scarcity"] == 0.0  # 6+ attractive alternatives -> fully saturated


def test_hitter_team_popularity_feature_matches_team_stats():
    hitters = small_slate_hitters()
    team_pop = compute_team_popularity(hitters)
    features = build_hitter_features(hitters, team_pop)
    for h in hitters:
        assert features[h.dk_player_id]["team_popularity"] == team_pop[h.team].team_popularity_score


def test_hitter_batting_order_effect_decreases_down_the_order():
    hitters = [hitter(f"h{i}", "AAA", ["OF"], 4000, 8.0, order=i) for i in range(1, 10)]
    features = build_hitter_features(hitters, {})
    assert features["h1"]["batting_order_effect"] > features["h9"]["batting_order_effect"]


def test_hitter_batting_order_unknown_uses_default():
    hitters = [hitter("h1", "AAA", ["OF"], 4000, 8.0, order=None)]
    features = build_hitter_features(hitters, {})
    assert features["h1"]["batting_order_effect"] == 50.0


def test_hitter_power_signal_from_tags():
    with_power = hitter("power1", "AAA", ["OF"], 4000, 8.0, tags=["elite_power", "elite_barrel"])
    without_power = hitter("no_power", "BBB", ["OF"], 4000, 8.0, tags=[])
    features = build_hitter_features([with_power, without_power], {})
    assert features["power1"]["power_signal"] > features["no_power"]["power_signal"]


def test_team_popularity_percentile_scaled_across_teams():
    hitters = small_slate_hitters()
    team_pop = compute_team_popularity(hitters)
    scores = [s.team_popularity_score for s in team_pop.values()]
    assert max(scores) == 100.0 or len(set(scores)) == 1
    assert all(0.0 <= s <= 100.0 for s in scores)


def test_multi_position_player_not_double_counted_in_own_scarcity():
    # min_1b_of eligible for both 1B and OF -- its OWN scarcity score
    # should reflect only its canonical (first-listed) position.
    hitters = [
        hitter("multi", "AAA", ["1B", "OF"], 4000, 8.0),
        hitter("of1", "BBB", ["OF"], 4000, 8.0),
        hitter("of2", "CCC", ["OF"], 4000, 8.0),
        hitter("of3", "DDD", ["OF"], 4000, 8.0),
    ]
    features = build_hitter_features(hitters, {})
    # multi's canonical position is 1B, with no other 1B alternatives at all
    # -> higher scarcity than the saturated 3-deep OF group.
    assert features["multi"]["position_scarcity"] > features["of1"]["position_scarcity"]


def test_sample_size_dampening_full_weight_above_threshold():
    p = hitter("h1", "AAA", ["OF"], 4000, 8.0, pa=300)
    assert sample_size_dampening(p) == 1.0


def test_sample_size_dampening_minimum_at_floor():
    p = hitter("h1", "AAA", ["OF"], 4000, 8.0, pa=4)
    from config.ownership_config import SAMPLE_SIZE_DAMPENING
    assert sample_size_dampening(p) == SAMPLE_SIZE_DAMPENING["min_dampening_factor"]


def test_sample_size_dampening_pitchers_always_full_weight():
    p = pitcher("p1", "AAA", 7000, 15.0)
    assert sample_size_dampening(p) == 1.0


def test_sample_size_dampening_interpolates_between_floor_and_threshold():
    low = hitter("h1", "AAA", ["OF"], 4000, 8.0, pa=50)
    high = hitter("h2", "AAA", ["OF"], 4000, 8.0, pa=140)
    assert sample_size_dampening(low) < sample_size_dampening(high) <= 1.0
