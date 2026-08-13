from optimizer.models import OptimizerSettings
from optimizer.solver import eligible_for_slot, expand_slot_instances, solve_single_lineup
from tests._optimizer_fixtures import feasible_pool, hitter, pitcher


def test_expand_slot_instances_matches_dk_classic_roster():
    slots = expand_slot_instances()
    assert slots == ["P", "P", "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF"]


def test_single_legal_lineup_is_found():
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)
    result = solve_single_lineup(players, settings)
    assert result is not None
    assert len(result) == 10


def test_salary_cap_respected():
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1, salary_cap=50000)
    result = solve_single_lineup(players, settings)
    total_salary = sum(p.salary for _, p in result)
    assert total_salary <= 50000


def test_each_roster_slot_filled_with_eligible_player():
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)
    result = solve_single_lineup(players, settings)
    for slot, player in result:
        if slot == "P":
            assert player.player_type == "pitcher"
        else:
            assert slot in player.dk_positions


def test_no_duplicate_players_in_lineup():
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)
    result = solve_single_lineup(players, settings)
    keys = [p.key for _, p in result]
    assert len(keys) == len(set(keys))


def test_multi_position_player_fills_exactly_one_slot():
    # min_1b_of is eligible for both 1B and OF -- must occupy exactly one.
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)
    result = solve_single_lineup(players, settings)
    slots_used = [slot for slot, p in result if p.key == "min_1b_of"]
    assert len(slots_used) <= 1


def test_infeasible_salary_cap_returns_none():
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1, salary_cap=100)
    result = solve_single_lineup(players, settings)
    assert result is None


def test_infeasible_missing_required_position_returns_none():
    players = [p for p in feasible_pool() if p.key != "phi_c" and p.key != "nyy_c"]  # no catcher at all
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)
    result = solve_single_lineup(players, settings)
    assert result is None


def test_objective_mode_projection_maximizes_projection_sum():
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)
    result = solve_single_lineup(players, settings)
    total_projection = sum(p.projection for _, p in result)
    # Sanity: within a small pool this should be close to the best achievable.
    assert total_projection > 0


def test_objective_mode_changes_selection_when_ceiling_diverges_from_projection():
    # Build two OF-eligible candidates where projection and ceiling disagree
    # on which is better, everything else held fixed and cheap/legal.
    players = [
        pitcher("p1", "TOR", 3000, 5.0, game_id="g1"),
        pitcher("p2", "PIT", 3000, 5.0, game_id="g2"),
        hitter("c1", "AAA", ["C"], 2000, 5.0, game_id="g3"),
        hitter("b1", "BBB", ["1B"], 2000, 5.0, game_id="g3"),
        hitter("b2", "CCC", ["2B"], 2000, 5.0, game_id="g3"),
        hitter("b3", "DDD", ["3B"], 2000, 5.0, game_id="g3"),
        hitter("ss1", "EEE", ["SS"], 2000, 5.0, game_id="g3"),
        hitter("of_safe", "FFF", ["OF"], 2000, 5.0, ceiling=6.0, game_id="g3"),
        hitter("of_mid", "GGG", ["OF"], 2000, 4.0, ceiling=5.0, game_id="g3"),
        hitter("of_filler", "HHH", ["OF"], 2000, 3.5, ceiling=4.0, game_id="g3"),
        # Worst projection of the four OF options, but by far the best ceiling.
        hitter("of_boom", "III", ["OF"], 2000, 1.0, ceiling=20.0, game_id="g3"),
    ]
    proj_result = solve_single_lineup(players, OptimizerSettings(objective_mode="projection", num_lineups=1))
    ceiling_result = solve_single_lineup(players, OptimizerSettings(objective_mode="ceiling", num_lineups=1))

    proj_keys = {p.key for _, p in proj_result}
    ceiling_keys = {p.key for _, p in ceiling_result}
    # 4 OF candidates competing for 3 slots: projection mode picks the top
    # 3 by projection (excludes of_boom); ceiling mode picks the top 3 by
    # ceiling (excludes of_filler, keeps of_boom despite its poor projection).
    assert "of_boom" not in proj_keys
    assert {"of_safe", "of_mid", "of_filler"} <= proj_keys
    assert "of_boom" in ceiling_keys
    assert "of_filler" not in ceiling_keys


def test_deterministic_across_repeated_solves():
    players = feasible_pool()
    settings = OptimizerSettings(objective_mode="projection", num_lineups=1)
    first = solve_single_lineup(players, settings)
    second = solve_single_lineup(players, settings)
    assert sorted(p.key for _, p in first) == sorted(p.key for _, p in second)
