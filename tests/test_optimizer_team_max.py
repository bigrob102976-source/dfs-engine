from config.dk_roster_config import DK_MAX_HITTERS_PER_TEAM
from optimizer.models import OptimizerSettings
from optimizer.solver import solve_single_lineup
from tests._optimizer_fixtures import hitter, team_max_pool


def test_team_hitter_max_is_five():
    assert DK_MAX_HITTERS_PER_TEAM == 5


def test_solver_never_exceeds_team_hitter_max_even_when_objective_wants_more():
    # PHI is structurally capable of filling 7 of 8 hitter slots and has
    # by far the best projections -- an unconstrained optimizer would
    # pick 7 PHI hitters. The team-max constraint must cap it at 5.
    players = team_max_pool()
    settings = OptimizerSettings(objective_mode="projection")
    result = solve_single_lineup(players, settings)
    assert result is not None
    phi_hitters = [p for _, p in result if p.player_type == "hitter" and p.team == "PHI"]
    assert len(phi_hitters) <= DK_MAX_HITTERS_PER_TEAM


def test_configurable_team_max_override_is_respected():
    # team_max_pool() only has 2 hitter-bearing teams (PHI, NYY); an
    # 8-hitter lineup capped at 3-per-team needs a 3rd team to stay legal.
    players = team_max_pool() + [
        hitter("cws_c", "CWS", ["C"], 2200, 5.0, opponent="CIN", game_id="g6"),
        hitter("cws_2b", "CWS", ["2B"], 2200, 5.0, opponent="CIN", game_id="g6"),
        hitter("cws_of", "CWS", ["OF"], 2200, 5.0, opponent="CIN", game_id="g6"),
    ]
    settings = OptimizerSettings(objective_mode="projection", team_max_hitters=3)
    result = solve_single_lineup(players, settings)
    assert result is not None
    phi_hitters = [p for _, p in result if p.player_type == "hitter" and p.team == "PHI"]
    assert len(phi_hitters) <= 3
