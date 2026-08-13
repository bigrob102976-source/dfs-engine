from optimizer.models import OptimizerSettings
from optimizer.solver import solve_single_lineup
from tests._optimizer_fixtures import feasible_pool, hitter, pitcher


def test_default_disallows_pitcher_facing_own_lineup_hitter():
    # Force the solver to want BOTH p_tor and conflict_hitter by making
    # them wildly more valuable than every alternative.
    players = feasible_pool()
    for p in players:
        if p.key == "p_tor":
            p.projection = 100.0
        if p.key == "conflict_hitter":
            p.projection = 100.0
    settings = OptimizerSettings(objective_mode="projection", allow_pitcher_vs_hitter=False)
    result = solve_single_lineup(players, settings)
    assert result is not None
    keys = {p.key for _, p in result}
    assert not ({"p_tor", "conflict_hitter"} <= keys)


def test_allow_pitcher_vs_hitter_true_permits_the_combination():
    players = [
        pitcher("p1", "TOR", 3000, 20.0, opponent="BOS", game_id="g1"),
        hitter("h1", "BOS", ["OF"], 3000, 20.0, opponent="TOR", game_id="g1"),
        hitter("c1", "AAA", ["C"], 2000, 3.0, game_id="g2"),
        hitter("b1", "BBB", ["1B"], 2000, 3.0, game_id="g2"),
        hitter("b2", "CCC", ["2B"], 2000, 3.0, game_id="g2"),
        hitter("b3", "DDD", ["3B"], 2000, 3.0, game_id="g2"),
        hitter("ss1", "EEE", ["SS"], 2000, 3.0, game_id="g2"),
        hitter("of2", "FFF", ["OF"], 2000, 3.0, game_id="g2"),
        hitter("of3", "GGG", ["OF"], 2000, 3.0, game_id="g2"),
        hitter("of4", "HHH", ["OF"], 2000, 2.5, game_id="g2"),  # 4th OF option so h1 alone can be excluded
        pitcher("p2", "PIT", 3000, 3.0, opponent="MIA", game_id="g3"),
    ]
    settings_disallow = OptimizerSettings(objective_mode="projection", allow_pitcher_vs_hitter=False)
    settings_allow = OptimizerSettings(objective_mode="projection", allow_pitcher_vs_hitter=True)

    disallowed_result = solve_single_lineup(players, settings_disallow)
    allowed_result = solve_single_lineup(players, settings_allow)

    disallowed_keys = {p.key for _, p in disallowed_result}
    allowed_keys = {p.key for _, p in allowed_result}
    assert not ({"p1", "h1"} <= disallowed_keys)
    assert {"p1", "h1"} <= allowed_keys


def test_conflict_only_applies_to_same_game():
    # p_atl (ATL) and conflict_hitter (BOS, facing TOR) are unrelated --
    # no conflict should be inferred just because both exist in the pool.
    players = feasible_pool()
    from optimizer.constraints import pitcher_vs_hitter_conflicts
    conflicts = pitcher_vs_hitter_conflicts(players)
    assert "p_atl" not in conflicts
    assert "p_pit" not in conflicts
    assert "p_hou" not in conflicts
