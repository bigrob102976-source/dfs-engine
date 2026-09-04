"""DK Classic MLB rule: a legal lineup must include players from at
least DK_MIN_GAMES_REPRESENTED (2) different games -- config/dk_roster_
config.py already defined this constant and dfs/roster_feasibility.py
already used it for a coarse POOL-level pre-check, but nothing
previously enforced it on the actual PER-LINEUP the solver picks (a
pool spanning 5 games could still have every lineup slot filled from a
single game). This file tests the fix: optimizer/solver.py's CP-SAT
constraint, optimizer/validator.py's independent re-check, and
optimizer/constraints.py's pre-solve diagnostic.
"""

from config.dk_roster_config import DK_MIN_GAMES_REPRESENTED
from optimizer.constraints import _concrete_infeasibility_reasons
from optimizer.lineup_generator import generate_lineups
from optimizer.models import Lineup, LineupPlayerAssignment, OptimizerSettings
from optimizer.solver import solve_single_lineup
from optimizer.validator import validate_lineup
from tests._optimizer_fixtures import feasible_pool, hitter, pitcher


def single_game_pool():
    """Every player -- pitchers included -- shares game_id 'only_game',
    so a legal 10-player lineup can only ever span exactly 1 game.
    Hitters are given a non-rostered opponent ("XXX", not TOR/BOS) so
    this fixture exercises ONLY the games-represented constraint, never
    tripping the separate, orthogonal pitcher-vs-hitter conflict rule
    (with only 2 pitchers total -- both required to fill the 2 P slots
    -- a real TOR/BOS opponent pairing here would make every hitter
    conflict with one pitcher or the other, an unrelated confound)."""
    return [
        pitcher("p1", "TOR", 7000, 18.0, opponent="BOS", game_id="only_game"),
        pitcher("p2", "BOS", 7000, 18.0, opponent="TOR", game_id="only_game"),
        hitter("c1", "TOR", ["C"], 2500, 8.0, opponent="XXX", game_id="only_game"),
        hitter("b1", "TOR", ["1B"], 2600, 8.0, opponent="XXX", game_id="only_game"),
        hitter("b2", "TOR", ["2B"], 2600, 8.0, opponent="XXX", game_id="only_game"),
        hitter("b3", "TOR", ["3B"], 2600, 8.0, opponent="XXX", game_id="only_game"),
        hitter("ss1", "TOR", ["SS"], 2600, 8.0, opponent="XXX", game_id="only_game"),
        hitter("of1", "BOS", ["OF"], 2600, 8.0, opponent="XXX", game_id="only_game"),
        hitter("of2", "BOS", ["OF"], 2600, 8.0, opponent="XXX", game_id="only_game"),
        hitter("of3", "BOS", ["OF"], 2600, 8.0, opponent="XXX", game_id="only_game"),
    ]


def test_default_min_games_represented_matches_dk_constant():
    assert OptimizerSettings().min_games_represented == DK_MIN_GAMES_REPRESENTED
    assert DK_MIN_GAMES_REPRESENTED == 2


def test_feasible_pool_naturally_satisfies_min_games_by_default():
    # Sanity check: the shared test fixture's pitchers/hitters already
    # span many distinct games, so the default constraint (now always
    # on) doesn't regress any pre-existing test built on this fixture.
    players = feasible_pool()
    result = solve_single_lineup(players, OptimizerSettings())
    assert result is not None
    games = {p.game_id for slot, p in result if p.game_id}
    assert len(games) >= DK_MIN_GAMES_REPRESENTED


def test_single_game_pool_is_infeasible_with_default_min_games():
    players = single_game_pool()
    result = solve_single_lineup(players, OptimizerSettings())
    assert result is None


def test_single_game_pool_is_feasible_when_min_games_relaxed_to_1():
    players = single_game_pool()
    result = solve_single_lineup(players, OptimizerSettings(min_games_represented=1))
    assert result is not None


def test_pre_solve_diagnostic_reports_insufficient_games():
    players = single_game_pool()
    reasons = _concrete_infeasibility_reasons(players, OptimizerSettings())
    assert any("game" in r.lower() for r in reasons)


def test_pre_solve_diagnostic_silent_when_min_games_relaxed():
    players = single_game_pool()
    reasons = _concrete_infeasibility_reasons(players, OptimizerSettings(min_games_represented=1))
    assert not any("game" in r.lower() and "DraftKings" in r for r in reasons)


def test_generate_lineups_respects_min_games_represented():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=3, min_unique=1))
    assert len(out.result.lineups) >= 1
    for lineup in out.result.lineups:
        games = {out.players_by_key[k].game_id for k in lineup.player_keys() if out.players_by_key[k].game_id}
        assert len(games) >= DK_MIN_GAMES_REPRESENTED


def _assignment(slot, player):
    return LineupPlayerAssignment(
        slot=slot, dk_player_id=player.key, mlb_player_id=player.mlb_player_id, name=player.name, team=player.team,
        opponent=player.opponent, salary=player.salary, projection=player.projection, ceiling=player.ceiling,
        floor=player.floor, risk_score=player.risk_score, confidence=player.confidence,
    )


def test_validator_flags_a_single_game_lineup():
    players = {p.key: p for p in single_game_pool()}
    assignments = [
        _assignment("P", players["p1"]), _assignment("P", players["p2"]),
        _assignment("C", players["c1"]), _assignment("1B", players["b1"]), _assignment("2B", players["b2"]),
        _assignment("3B", players["b3"]), _assignment("SS", players["ss1"]),
        _assignment("OF", players["of1"]), _assignment("OF", players["of2"]), _assignment("OF", players["of3"]),
    ]
    salary = sum(a.salary for a in assignments)
    lineup = Lineup(
        index=1, assignments=assignments, salary=salary, remaining_salary=50000 - salary,
        projection=sum(a.projection for a in assignments), ceiling=sum(a.ceiling for a in assignments),
        floor=sum(a.floor for a in assignments), average_risk=30.0, average_confidence=90.0,
        team_counts={}, primary_stack_team=None, primary_stack_size=0,
    )
    violations = validate_lineup(lineup, players, OptimizerSettings())
    assert any("game" in v.lower() for v in violations)


def test_validator_passes_a_two_game_lineup():
    by_key = {p.key: p for p in feasible_pool()}
    assignments = [
        _assignment("P", by_key["p_tor"]), _assignment("P", by_key["p_pit"]), _assignment("C", by_key["phi_c"]),
        _assignment("1B", by_key["phi_1b"]), _assignment("2B", by_key["phi_2b"]), _assignment("3B", by_key["phi_3b"]),
        _assignment("SS", by_key["phi_ss"]), _assignment("OF", by_key["nyy_of1"]), _assignment("OF", by_key["nyy_of2"]),
        _assignment("OF", by_key["nyy_of3"]),
    ]
    salary = sum(a.salary for a in assignments)
    lineup = Lineup(
        index=1, assignments=assignments, salary=salary, remaining_salary=50000 - salary,
        projection=sum(a.projection for a in assignments), ceiling=sum(a.ceiling for a in assignments),
        floor=sum(a.floor for a in assignments), average_risk=30.0, average_confidence=90.0,
        team_counts={}, primary_stack_team=None, primary_stack_size=0,
    )
    violations = validate_lineup(lineup, by_key, OptimizerSettings())
    assert not any("game" in v.lower() for v in violations)
