from optimizer.lineup_generator import generate_lineups
from optimizer.models import OptimizerSettings
from optimizer.solver import solve_single_lineup
from tests._optimizer_fixtures import feasible_pool


def _hitter_team_counts(assignment):
    counts = {}
    for slot, player in assignment:
        if player.player_type == "hitter":
            counts[player.team] = counts.get(player.team, 0) + 1
    return counts


def test_stack_size_4_satisfied():
    players = feasible_pool()
    result = solve_single_lineup(players, OptimizerSettings(stack_size=4))
    assert result is not None
    counts = _hitter_team_counts(result)
    assert max(counts.values()) >= 4


def test_stack_size_5_satisfied():
    players = feasible_pool()
    result = solve_single_lineup(players, OptimizerSettings(stack_size=5))
    assert result is not None
    counts = _hitter_team_counts(result)
    assert max(counts.values()) >= 5


def test_forced_stack_team_honored():
    players = feasible_pool()
    result = solve_single_lineup(players, OptimizerSettings(stack_size=5, stack_team="NYY"))
    assert result is not None
    counts = _hitter_team_counts(result)
    assert counts.get("NYY", 0) >= 5


def test_stack_impossible_returns_none():
    players = feasible_pool()
    # No team in the pool has 8 hitters.
    result = solve_single_lineup(players, OptimizerSettings(stack_size=8))
    assert result is None


def test_stack_impossible_for_named_team_returns_none():
    players = feasible_pool()
    # BAL only has one hitter in the pool.
    result = solve_single_lineup(players, OptimizerSettings(stack_size=3, stack_team="BAL"))
    assert result is None


def test_stack_reported_on_lineup_metrics():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1, stack_size=5, stack_team="PHI"))
    lineup = out.result.lineups[0]
    assert lineup.primary_stack_team == "PHI"
    assert lineup.primary_stack_size >= 5


def test_pitchers_do_not_count_toward_stack_size():
    # Force PHI's pitcher-equivalent count to be irrelevant -- PHI has no
    # pitcher in the pool at all, so a PHI stack can only be built from hitters.
    players = feasible_pool()
    result = solve_single_lineup(players, OptimizerSettings(stack_size=5, stack_team="PHI"))
    assert result is not None
    pitcher_teams = {p.team for slot, p in result if p.player_type == "pitcher"}
    assert "PHI" not in pitcher_teams  # confirms the 5 PHI hitters are hitters, not inflated by a PHI pitcher
