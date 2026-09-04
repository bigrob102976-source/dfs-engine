import pytest

from optimizer.constraints import OptimizerConfigError, resolve_settings
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


# ---------------------------------------------------------------------------
# Multi-team stacks (M2): 5-3 / 5-2 / 4-4 / 4-3. feasible_pool() has PHI (7
# hitters) and NYY (5 hitters) -- large enough to cover every combination
# below (max combined need is 5+3=8, exactly DK's 8 hitter roster slots).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("primary_size,secondary_size", [(5, 3), (5, 2), (4, 4), (4, 3)])
def test_two_team_stack_satisfied(primary_size, secondary_size):
    players = feasible_pool()
    settings = OptimizerSettings(
        stack_size=primary_size, stack_team="PHI", stack_size_2=secondary_size, stack_team_2="NYY",
    )
    result = solve_single_lineup(players, settings)
    assert result is not None
    counts = _hitter_team_counts(result)
    assert counts.get("PHI", 0) >= primary_size
    assert counts.get("NYY", 0) >= secondary_size


def test_two_team_stack_reported_on_lineup_metrics():
    players = feasible_pool()
    settings = OptimizerSettings(num_lineups=1, stack_size=5, stack_team="PHI", stack_size_2=3, stack_team_2="NYY")
    out = generate_lineups(players, settings)
    lineup = out.result.lineups[0]
    assert lineup.primary_stack_team == "PHI"
    assert lineup.primary_stack_size >= 5
    assert lineup.secondary_stack_team == "NYY"
    assert lineup.secondary_stack_size >= 3


def test_two_team_stack_same_team_rejected():
    players = feasible_pool()
    settings = OptimizerSettings(stack_size=5, stack_team="PHI", stack_size_2=3, stack_team_2="PHI")
    with pytest.raises(OptimizerConfigError, match="must be different"):
        resolve_settings(players, settings)


def test_two_team_stack_requires_explicit_primary_team():
    # No AUTO primary allowed for a two-team stack -- stack_team must be set.
    players = feasible_pool()
    settings = OptimizerSettings(stack_size=5, stack_size_2=3, stack_team_2="NYY")
    with pytest.raises(OptimizerConfigError, match="explicit primary"):
        resolve_settings(players, settings)


def test_two_team_stack_requires_stack_team_2():
    players = feasible_pool()
    settings = OptimizerSettings(stack_size=5, stack_team="PHI", stack_size_2=3)
    with pytest.raises(OptimizerConfigError, match="--stack-team-2"):
        resolve_settings(players, settings)


def test_stack_team_2_without_stack_size_2_raises():
    players = feasible_pool()
    settings = OptimizerSettings(stack_team_2="NYY")
    with pytest.raises(OptimizerConfigError, match="--stack-size-2"):
        resolve_settings(players, settings)


def test_two_team_stack_insufficient_secondary_hitters_returns_none():
    players = feasible_pool()
    # BAL only has one hitter in the pool -- can never satisfy a 3-hitter secondary stack.
    settings = OptimizerSettings(stack_size=5, stack_team="PHI", stack_size_2=3, stack_team_2="BAL")
    result = solve_single_lineup(players, settings)
    assert result is None


def test_two_team_stack_with_lock_honored():
    players = feasible_pool()
    settings = OptimizerSettings(
        num_lineups=1, stack_size=5, stack_team="PHI", stack_size_2=3, stack_team_2="NYY", locks=["Phi C"],
    )
    out = generate_lineups(players, settings)
    lineup = out.result.lineups[0]
    assert "phi_c" in lineup.player_keys()
    counts = {}
    for a in lineup.assignments:
        player = out.players_by_key[a.dk_player_id]
        if player.player_type == "hitter":
            counts[a.team] = counts.get(a.team, 0) + 1
    assert counts.get("PHI", 0) >= 5
    assert counts.get("NYY", 0) >= 3


def test_two_team_stack_with_exclude_makes_infeasible():
    players = feasible_pool()
    # Excluding 3 of PHI's 7 hitters leaves only 4 -- not enough for a 5-hitter primary stack.
    settings = OptimizerSettings(stack_size=5, stack_team="PHI", stack_size_2=3, stack_team_2="NYY")
    forced_excludes = {"phi_of1", "phi_of2", "phi_ss"}
    result = solve_single_lineup(players, settings, forced_excludes=forced_excludes)
    assert result is None


def test_two_team_stack_respects_exposure_cap():
    players = feasible_pool()
    # 4 lineups, PHI's cheapest/only catcher capped at 50% (<=2 of 4).
    settings = OptimizerSettings(
        num_lineups=4, stack_size=5, stack_team="PHI", stack_size_2=3, stack_team_2="NYY",
        max_exposure={"Phi C": 0.5},
    )
    out = generate_lineups(players, settings)
    assert len(out.result.lineups) >= 1  # some lineups generated
    appearances = sum(1 for lu in out.result.lineups if "phi_c" in lu.player_keys())
    assert appearances <= out.exposure_caps["phi_c"]
    for lu in out.result.lineups:
        counts = {}
        for a in lu.assignments:
            player = out.players_by_key[a.dk_player_id]
            if player.player_type == "hitter":
                counts[a.team] = counts.get(a.team, 0) + 1
        assert counts.get("PHI", 0) >= 5
        assert counts.get("NYY", 0) >= 3
