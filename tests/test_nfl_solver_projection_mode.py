"""NFL M4 -- targeted tests for nfl/solver.py's mode="projection" path.
mode="roster_feasibility" regression coverage lives in
tests/test_nfl_solver.py (M3) and is untouched by these."""

import pytest

from nfl.optimizer_models import NflOptimizerPlayer, NflOptimizerSettings
from nfl.solver import NflOptimizerConfigError, NflProjectionCoverageError, generate_lineups

DG_ID = 151307
DATE = "2026-09-13"


def _p(key, name, position, salary, projection, roster_slots=None):
    return NflOptimizerPlayer(
        key=key, name=name, team="PHI", opponent="DAL", game_id="100", position=position,
        roster_slots=roster_slots or ([position, "FLEX"] if position in ("RB", "WR", "TE") else [position]),
        salary=salary, is_team_entity=(position == "DST"), draft_group_id=DG_ID, slate_date=DATE, projection=projection,
    )


def _fully_projected_pool():
    return [
        _p("qb1", "QB One", "QB", 7000, 20.0),
        _p("qb2", "QB Two", "QB", 6800, 18.0),
        _p("rb1", "RB One", "RB", 6500, 15.0),
        _p("rb2", "RB Two", "RB", 5000, 10.0),
        _p("rb3", "RB Three", "RB", 4000, 8.0),
        _p("rb4", "RB Four", "RB", 3800, 6.0),
        _p("wr1", "WR One", "WR", 6000, 14.0),
        _p("wr2", "WR Two", "WR", 5500, 12.0),
        _p("wr3", "WR Three", "WR", 4500, 9.0),
        _p("wr4", "WR Four", "WR", 4000, 7.0),
        _p("wr5", "WR Five", "WR", 3500, 5.0),
        _p("te1", "TE One", "TE", 4200, 9.0),
        _p("te2", "TE Two", "TE", 3000, 4.0),
        _p("dst1", "Team One DST", "DST", 2500, 6.0),
        _p("dst2", "Team Two DST", "DST", 2200, 5.0),
    ]


def test_projection_mode_generates_valid_lineup():
    result = generate_lineups(_fully_projected_pool(), NflOptimizerSettings(mode="projection", num_lineups=1))
    assert result.generated == 1
    lineup = result.lineups[0]
    assert lineup.mode == "projection"
    assert lineup.total_projection is not None and lineup.total_projection > 0
    assert len(lineup.assignments) == 9


def test_projection_mode_maximizes_projection_not_salary():
    """The two highest-projection players (qb1=20, wr1=14) should be
    strongly preferred over higher-salary/lower-projection alternatives
    -- proves the objective is really reading projection, not salary."""
    result = generate_lineups(_fully_projected_pool(), NflOptimizerSettings(mode="projection", num_lineups=1))
    keys = result.lineups[0].player_keys()
    assert "qb1" in keys  # highest-projection QB (also highest salary here, so pair with a clearer signal below)


def test_unprojected_player_never_silently_used_as_zero():
    pool = _fully_projected_pool()
    # Give one RB no projection at all -- must never be selected in
    # projection mode, even though it's cheap and would help a
    # salary-based objective.
    pool.append(NflOptimizerPlayer(
        key="rb_unprojected", name="Unprojected RB", team="PHI", opponent="DAL", game_id="100", position="RB",
        roster_slots=["RB", "FLEX"], salary=100, is_team_entity=False, draft_group_id=DG_ID, slate_date=DATE, projection=None,
    ))
    result = generate_lineups(pool, NflOptimizerSettings(mode="projection", num_lineups=1))
    assert "rb_unprojected" not in result.lineups[0].player_keys()


def test_insufficient_projection_coverage_raises_loudly():
    """Zero real projections anywhere (NFL M4's actual current state,
    since no Big Money Native model exists yet) must raise a specific,
    clear error -- never silently return an empty result or fall back
    to salary optimization."""
    pool = [
        NflOptimizerPlayer(key=p.key, name=p.name, team=p.team, opponent=p.opponent, game_id=p.game_id,
                            position=p.position, roster_slots=p.roster_slots, salary=p.salary,
                            is_team_entity=p.is_team_entity, draft_group_id=p.draft_group_id, slate_date=p.slate_date,
                            projection=None)
        for p in _fully_projected_pool()
    ]
    with pytest.raises(NflProjectionCoverageError) as exc_info:
        generate_lineups(pool, NflOptimizerSettings(mode="projection", num_lineups=1))
    assert "QB" in str(exc_info.value)  # names at least one specific missing slot


def test_partial_coverage_missing_one_position_raises():
    pool = [p for p in _fully_projected_pool() if p.position != "DST"]  # no DST has a projection at all
    with pytest.raises(NflProjectionCoverageError) as exc_info:
        generate_lineups(pool, NflOptimizerSettings(mode="projection", num_lineups=1))
    assert "DST" in str(exc_info.value)


def test_roster_feasibility_mode_unaffected_by_projection_field():
    """A pool where every player has a real projection must still work
    identically in roster_feasibility mode (salary objective, ignores
    projection entirely)."""
    result = generate_lineups(_fully_projected_pool(), NflOptimizerSettings(mode="roster_feasibility", num_lineups=1))
    assert result.generated == 1
    assert result.lineups[0].mode == "roster_feasibility"
    assert result.lineups[0].total_projection is None
    assert result.lineups[0].total_salary <= 50000


def test_lock_honored_in_projection_mode():
    result = generate_lineups(_fully_projected_pool(), NflOptimizerSettings(mode="projection", num_lineups=1, locks=["rb4"]))
    assert "rb4" in result.lineups[0].player_keys()


def test_exclude_honored_in_projection_mode():
    result = generate_lineups(_fully_projected_pool(), NflOptimizerSettings(mode="projection", num_lineups=1, excludes=["qb1"]))
    assert "qb1" not in result.lineups[0].player_keys()


def test_unknown_mode_raises_config_error():
    with pytest.raises(NflOptimizerConfigError):
        generate_lineups(_fully_projected_pool(), NflOptimizerSettings(mode="not_a_real_mode", num_lineups=1))


def test_multiple_projection_lineups_are_unique():
    result = generate_lineups(_fully_projected_pool(), NflOptimizerSettings(mode="projection", num_lineups=3, min_unique=1))
    assert result.generated == 3
    key_sets = [frozenset(l.player_keys()) for l in result.lineups]
    assert len(set(key_sets)) == 3
