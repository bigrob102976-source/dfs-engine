"""NFL M3 -- targeted tests for nfl/solver.py's roster-feasibility CP-SAT
solver. All fixtures are synthetic; no network calls, no fabricated
projections (NflOptimizerPlayer has no projection field at all)."""

import pytest

from nfl.optimizer_models import NflOptimizerPlayer, NflOptimizerSettings
from nfl.solver import NflOptimizerConfigError, generate_lineups

DG_ID = 151307
DATE = "2026-09-13"


def _p(key, name, position, salary, roster_slots=None, team="PHI", opponent="DAL"):
    return NflOptimizerPlayer(
        key=key, name=name, team=team, opponent=opponent, game_id="100", position=position,
        roster_slots=roster_slots or ([position, "FLEX"] if position in ("RB", "WR", "TE") else [position]),
        salary=salary, is_team_entity=(position == "DST"), draft_group_id=DG_ID, slate_date=DATE,
    )


def _full_pool():
    return [
        _p("qb1", "QB One", "QB", 7000),
        _p("qb2", "QB Two", "QB", 6800),
        _p("rb1", "RB One", "RB", 6500),
        _p("rb2", "RB Two", "RB", 5000),
        _p("rb3", "RB Three", "RB", 4000),
        _p("rb4", "RB Four", "RB", 3800),
        _p("wr1", "WR One", "WR", 6000),
        _p("wr2", "WR Two", "WR", 5500),
        _p("wr3", "WR Three", "WR", 4500),
        _p("wr4", "WR Four", "WR", 4000),
        _p("wr5", "WR Five", "WR", 3500),
        _p("te1", "TE One", "TE", 4200),
        _p("te2", "TE Two", "TE", 3000),
        _p("dst1", "Team One DST", "DST", 2500),
        _p("dst2", "Team Two DST", "DST", 2200),
    ]


def test_generates_one_legal_lineup():
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1))
    assert result.generated == 1
    lineup = result.lineups[0]
    assert len(lineup.assignments) == 9
    assert lineup.total_salary <= 50000
    assert lineup.mode == "roster_feasibility"
    slots = sorted(a.slot for a in lineup.assignments)
    assert slots == ["DST", "FLEX", "QB", "RB1", "RB2", "TE", "WR1", "WR2", "WR3"]


def test_flex_slot_filled_by_a_flex_eligible_player():
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1))
    lineup = result.lineups[0]
    flex_assignment = next(a for a in lineup.assignments if a.slot == "FLEX")
    assert flex_assignment.position in ("RB", "WR", "TE")


def test_qb_and_dst_never_assigned_to_flex():
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1))
    lineup = result.lineups[0]
    flex_assignment = next(a for a in lineup.assignments if a.slot == "FLEX")
    assert flex_assignment.position not in ("QB", "DST")


def test_lock_is_honored():
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1, locks=["rb4"]))
    assert result.generated == 1
    assert "rb4" in result.lineups[0].player_keys()


def test_exclude_is_honored():
    # rb1 is the highest-salary RB -- excluding it must remove it from
    # the generated lineup entirely, never silently substituted back in.
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1, excludes=["rb1"]))
    assert result.generated == 1
    assert "rb1" not in result.lineups[0].player_keys()


def test_multiple_lineups_are_unique():
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=3, min_unique=1))
    assert result.generated == 3
    key_sets = [frozenset(l.player_keys()) for l in result.lineups]
    assert len(set(key_sets)) == 3  # all three genuinely distinct


def test_unknown_lock_key_raises():
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1, locks=["does-not-exist"]))


def test_lock_and_exclude_conflict_raises():
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1, locks=["qb1"], excludes=["qb1"]))


def test_too_many_locks_raises():
    pool = _full_pool()
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(pool, NflOptimizerSettings(num_lineups=1, locks=[p.key for p in pool]))  # 15 locks, 9 slots


def test_impossible_lock_set_fails_loudly_not_silently():
    """Locking both real QBs is structurally impossible (exactly 1 QB
    slot, QB is never FLEX-eligible) -- the solver must report this
    clearly (generated=0, a real stopped_reason), never silently drop
    one of the locks or return an illegal lineup."""
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1, locks=["qb1", "qb2"]))
    assert result.generated == 0
    assert result.stopped_reason is not None and "No legal lineup found" in result.stopped_reason


def test_salary_cap_never_exceeded():
    result = generate_lineups(_full_pool(), NflOptimizerSettings(num_lineups=1, salary_cap=30000))
    # A tighter cap than the cheapest legal combination allows should
    # either find a legal (cheaper) lineup respecting it, or fail loudly.
    if result.generated:
        assert result.lineups[0].total_salary <= 30000
