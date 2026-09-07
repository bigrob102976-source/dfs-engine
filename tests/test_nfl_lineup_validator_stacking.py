"""NFL M13 -- targeted tests for nfl/lineup_validator.py's stacking/
bring-back/RB+DST/team+game-limit/exposure independent re-checks."""

from nfl.lineup_validator import validate_lineup, validate_lineup_set
from nfl.optimizer_models import NflOptimizerSettings, NflStackConfig
from nfl.solver import generate_lineups
from tests._nfl_stack_fixtures import multi_team_pool


def _players_by_key(pool):
    return {p.key: p for p in pool}


def test_valid_single_stack_lineup_passes_stack_validation():
    pool = multi_team_pool()
    stack = NflStackConfig(qb_stack_mode="single")
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=1, stack=stack))
    lineup = result.lineups[0]
    violations = validate_lineup(lineup, _players_by_key(pool), stack=stack)
    assert violations == []


def test_lineup_missing_stack_is_flagged_when_checked_against_a_stricter_config():
    """A lineup built with NO stack requirement, re-validated against a
    stricter double-stack config, must be flagged -- proves the
    validator independently re-derives the check rather than trusting
    the lineup's own metadata."""
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=1))  # no stack
    lineup = result.lineups[0]
    strict_stack = NflStackConfig(qb_stack_mode="double")
    violations = validate_lineup(lineup, _players_by_key(pool), stack=strict_stack)
    # Only assert a violation IF this particular lineup genuinely doesn't
    # meet a double stack (extremely likely with no stack requested, but
    # avoid a flaky false failure if the solver happened to pick 2 same-team
    # receivers anyway).
    qb = next(a for a in lineup.assignments if a.position == "QB")
    catchers = [a for a in lineup.assignments if a.position in ("WR", "TE") and a.team == qb.team]
    if len(catchers) < 2:
        assert any("QB stack requirement" in v for v in violations)


def test_valid_bring_back_lineup_passes_validation():
    pool = multi_team_pool()
    stack = NflStackConfig(qb_stack_mode="single", bring_back_mode="one")
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=1, stack=stack))
    lineup = result.lineups[0]
    violations = validate_lineup(lineup, _players_by_key(pool), stack=stack)
    assert violations == []


def test_missing_bring_back_is_flagged():
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=1))  # no bring-back requested
    lineup = result.lineups[0]
    strict_stack = NflStackConfig(qb_stack_mode="single", bring_back_mode="one")
    qb = next(a for a in lineup.assignments if a.position == "QB")
    opponent = next(p.opponent for p in pool if p.team == qb.team)
    bb = [a for a in lineup.assignments if a.position in ("RB", "WR", "TE") and a.team == opponent]
    violations = validate_lineup(lineup, _players_by_key(pool), stack=strict_stack)
    if not bb:
        assert any("Bring-back requirement" in v for v in violations)


def test_valid_rb_dst_lineup_passes_validation():
    pool = multi_team_pool()
    stack = NflStackConfig(rb_dst_enabled=True)
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=1, stack=stack))
    lineup = result.lineups[0]
    violations = validate_lineup(lineup, _players_by_key(pool), stack=stack)
    assert violations == []


def test_max_players_per_team_violation_detected():
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=1))
    lineup = result.lineups[0]
    team_counts = {}
    for a in lineup.assignments:
        team_counts[a.team] = team_counts.get(a.team, 0) + 1
    strict_stack = NflStackConfig(max_players_per_team=1)
    violations = validate_lineup(lineup, _players_by_key(pool), stack=strict_stack)
    if any(c > 1 for c in team_counts.values()):
        assert any("exceeds max_players_per_team" in v for v in violations)


def test_validate_lineup_set_flags_exposure_cap_violation():
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=5, locks=["TMA_dst"], min_unique=1))
    results = validate_lineup_set(result.lineups, _players_by_key(pool), max_exposure_caps={"TMA_dst": 3})
    flagged = [v for violations in results.values() for v in violations if "Exposure cap exceeded" in v]
    assert flagged  # locked in all 5 lineups, cap of 3 -- must be flagged


def test_validate_lineup_set_flags_min_exposure_target_miss():
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=3, excludes=["TMD_te"], min_unique=1))
    results = validate_lineup_set(result.lineups, _players_by_key(pool), min_exposure_targets={"TMD_te": 2})
    flagged = [v for violations in results.values() for v in violations if "Exposure target not met" in v]
    assert flagged  # excluded entirely -- target of 2 can never be met


def test_validate_lineup_set_no_violations_on_clean_batch():
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=3, min_unique=1))
    results = validate_lineup_set(result.lineups, _players_by_key(pool), min_unique=1)
    all_violations = [v for violations in results.values() for v in violations]
    assert all_violations == []


def test_validate_lineup_set_flags_pairwise_uniqueness_violation():
    pool = multi_team_pool()
    result = generate_lineups(pool, NflOptimizerSettings(num_lineups=2, min_unique=1))
    lineups = result.lineups
    results = validate_lineup_set(lineups, _players_by_key(pool), min_unique=9)  # every lineup must be TOTALLY different
    all_violations = [v for violations in results.values() for v in violations]
    assert any("differ by only" in v for v in all_violations)
