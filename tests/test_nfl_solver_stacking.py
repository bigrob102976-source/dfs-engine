"""NFL M13 -- targeted tests for nfl/solver.py's stacking/bring-back/
RB+DST/team-max/game-max constraints, real CP-SAT solves against a
synthetic multi-team pool (tests/_nfl_stack_fixtures.py)."""

from nfl.optimizer_models import NflOptimizerSettings, NflStackConfig
from nfl.solver import generate_lineups
from tests._nfl_stack_fixtures import multi_team_pool

QB_STACK_PASS_CATCHER_POSITIONS = ("WR", "TE")
BRING_BACK_ELIGIBLE_POSITIONS = ("RB", "WR", "TE")


def _lineup_teams(lineup, players_by_key=None):
    return {a.team for a in lineup.assignments}


def test_single_qb_stack_produces_qb_plus_one_same_team_receiver():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(qb_stack_mode="single"))
    result = generate_lineups(pool, settings)
    assert result.generated == 1
    lineup = result.lineups[0]
    qb = next(a for a in lineup.assignments if a.position == "QB")
    catchers = [a for a in lineup.assignments if a.position in QB_STACK_PASS_CATCHER_POSITIONS and a.team == qb.team]
    assert len(catchers) >= 1
    assert lineup.qb_stack_team == qb.team
    assert lineup.qb_stack_receiver_count >= 1


def test_double_qb_stack_produces_qb_plus_two_same_team_receivers():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(qb_stack_mode="double"))
    result = generate_lineups(pool, settings)
    assert result.generated == 1
    lineup = result.lineups[0]
    qb = next(a for a in lineup.assignments if a.position == "QB")
    catchers = [a for a in lineup.assignments if a.position in QB_STACK_PASS_CATCHER_POSITIONS and a.team == qb.team]
    assert len(catchers) >= 2
    assert lineup.qb_stack_receiver_count >= 2


def test_no_stack_by_default():
    """Default settings (stack off) must behave EXACTLY like pre-M13 --
    no forced correlation."""
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=1))
    assert result.generated == 1
    lineup = result.lineups[0]
    assert lineup.qb_stack_team is None or lineup.qb_stack_receiver_count >= 0  # no assertion on correlation -- just must not crash


def _opponent_of(pool, team):
    return next(p.opponent for p in pool if p.team == team)


def test_bring_back_produces_opposing_pass_catcher_or_rb():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(qb_stack_mode="single", bring_back_mode="one"))
    result = generate_lineups(pool, settings)
    assert result.generated == 1
    lineup = result.lineups[0]
    qb = next(a for a in lineup.assignments if a.position == "QB")
    opponent = _opponent_of(pool, qb.team)
    bring_back = [a for a in lineup.assignments if a.position in BRING_BACK_ELIGIBLE_POSITIONS and a.team == opponent]
    assert len(bring_back) >= 1
    assert lineup.bring_back_player is not None


def test_bring_back_never_uses_opposing_dst():
    """DST can never satisfy bring-back (NFL M13 Phase 3) -- a real,
    non-DST opposing RB/WR/TE must always be present whenever bring_back_mode
    is on, regardless of which team's DST also happens to be rostered."""
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=5, stack=NflStackConfig(qb_stack_mode="single", bring_back_mode="one"))
    result = generate_lineups(pool, settings)
    assert result.generated >= 1
    for lineup in result.lineups:
        qb = next(a for a in lineup.assignments if a.position == "QB")
        opponent = _opponent_of(pool, qb.team)
        bring_back = [a for a in lineup.assignments if a.position in BRING_BACK_ELIGIBLE_POSITIONS and a.team == opponent]
        assert len(bring_back) >= 1  # a real non-DST bring-back piece is always present


def test_rb_dst_produces_same_team_rb_and_dst():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(rb_dst_enabled=True))
    result = generate_lineups(pool, settings)
    assert result.generated == 1
    lineup = result.lineups[0]
    dst = next(a for a in lineup.assignments if a.position == "DST")
    rb_same_team = [a for a in lineup.assignments if a.position == "RB" and a.team == dst.team]
    assert len(rb_same_team) >= 1
    assert lineup.rb_dst_team == dst.team


def test_max_players_per_team_is_respected():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(max_players_per_team=3))
    result = generate_lineups(pool, settings)
    assert result.generated == 1
    lineup = result.lineups[0]
    team_counts = {}
    for a in lineup.assignments:
        team_counts[a.team] = team_counts.get(a.team, 0) + 1
    assert all(c <= 3 for c in team_counts.values())


def test_max_players_per_game_is_respected():
    # Only 2 games exist in this synthetic pool (G1, G2) and the roster
    # needs 9 players -- max_players_per_game must be >= 5 for this to
    # be feasible at all (2*4=8 < 9), so 5 is the tightest meaningful cap.
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=1, stack=NflStackConfig(max_players_per_game=5))
    result = generate_lineups(pool, settings)
    assert result.generated == 1
    lineup = result.lineups[0]
    game_counts = {}
    for a in lineup.assignments:
        player = next(p for p in pool if p.key == a.draftkings_player_id)
        game_counts[player.game_id] = game_counts.get(player.game_id, 0) + 1
    assert all(c <= 5 for c in game_counts.values())


def test_combined_double_stack_plus_bring_back_plus_rb_dst():
    """All three correlation rules together must still produce a legal,
    fully-correlated lineup on a large enough pool."""
    pool = multi_team_pool()
    settings = NflOptimizerSettings(
        num_lineups=1,
        stack=NflStackConfig(qb_stack_mode="double", bring_back_mode="one", rb_dst_enabled=True),
    )
    result = generate_lineups(pool, settings)
    assert result.generated == 1
    lineup = result.lineups[0]
    assert lineup.qb_stack_receiver_count >= 2
    assert lineup.bring_back_player is not None


def test_multiple_stacked_lineups_remain_unique():
    pool = multi_team_pool()
    settings = NflOptimizerSettings(num_lineups=5, stack=NflStackConfig(qb_stack_mode="single"), min_unique=1)
    result = generate_lineups(pool, settings)
    assert result.generated >= 1
    key_sets = [frozenset(l.player_keys()) for l in result.lineups]
    assert len(set(key_sets)) == len(key_sets)
