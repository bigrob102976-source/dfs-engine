from optimizer.models import Lineup, LineupPlayerAssignment, OptimizerSettings
from optimizer.validator import validate_lineup, validate_lineup_set
from tests._optimizer_fixtures import feasible_pool


def _players_by_key():
    return {p.key: p for p in feasible_pool()}


def _assignment(slot, player):
    return LineupPlayerAssignment(
        slot=slot, dk_player_id=player.key, mlb_player_id=player.mlb_player_id, name=player.name, team=player.team,
        opponent=player.opponent, salary=player.salary, projection=player.projection, ceiling=player.ceiling,
        floor=player.floor, risk_score=player.risk_score, confidence=player.confidence,
    )


def _legal_assignments(players_by_key):
    slots_and_keys = [
        ("P", "p_tor"), ("P", "p_pit"), ("C", "phi_c"), ("1B", "phi_1b"), ("2B", "phi_2b"),
        ("3B", "phi_3b"), ("SS", "phi_ss"), ("OF", "nyy_of1"), ("OF", "nyy_of2"), ("OF", "nyy_of3"),
    ]
    return [_assignment(slot, players_by_key[key]) for slot, key in slots_and_keys]


def _lineup(assignments, index=1):
    salary = sum(a.salary for a in assignments)
    return Lineup(
        index=index, assignments=assignments, salary=salary, remaining_salary=50000 - salary,
        projection=sum(a.projection for a in assignments), ceiling=sum(a.ceiling for a in assignments),
        floor=sum(a.floor for a in assignments), average_risk=30.0, average_confidence=90.0,
        team_counts={}, primary_stack_team=None, primary_stack_size=0,
    )


def test_legal_lineup_has_no_violations():
    by_key = _players_by_key()
    lineup = _lineup(_legal_assignments(by_key))
    violations = validate_lineup(lineup, by_key, OptimizerSettings())
    assert violations == []


def test_wrong_roster_size_detected():
    by_key = _players_by_key()
    assignments = _legal_assignments(by_key)[:-1]  # drop one OF
    lineup = _lineup(assignments)
    violations = validate_lineup(lineup, by_key, OptimizerSettings())
    assert any("Roster size" in v for v in violations)


def test_wrong_slot_count_detected():
    by_key = _players_by_key()
    assignments = _legal_assignments(by_key)
    assignments[-1] = _assignment("C", by_key["nyy_c"])  # now 2 C, 2 OF instead of 1 C / 3 OF
    lineup = _lineup(assignments)
    violations = validate_lineup(lineup, by_key, OptimizerSettings())
    assert any("Slot C" in v or "Slot OF" in v for v in violations)


def test_position_ineligibility_detected():
    by_key = _players_by_key()
    assignments = _legal_assignments(by_key)
    assignments[2] = _assignment("C", by_key["phi_1b"])  # phi_1b is not C-eligible
    lineup = _lineup(assignments)
    violations = validate_lineup(lineup, by_key, OptimizerSettings())
    assert any("not DK-eligible" in v for v in violations)


def test_salary_over_cap_detected():
    by_key = _players_by_key()
    lineup = _lineup(_legal_assignments(by_key))
    settings = OptimizerSettings(salary_cap=1000)
    violations = validate_lineup(lineup, by_key, settings)
    assert any("exceeds cap" in v for v in violations)


def test_duplicate_player_detected():
    by_key = _players_by_key()
    assignments = _legal_assignments(by_key)
    assignments[-1] = _assignment("OF", by_key["nyy_of1"])  # duplicate of assignments[-3]
    lineup = _lineup(assignments)
    violations = validate_lineup(lineup, by_key, OptimizerSettings())
    assert any("Duplicate" in v for v in violations)


def test_missing_lock_detected():
    by_key = _players_by_key()
    lineup = _lineup(_legal_assignments(by_key))
    violations = validate_lineup(lineup, by_key, OptimizerSettings(), locked_keys=["conflict_hitter"])
    assert any("Locked player" in v for v in violations)


def test_present_exclude_detected():
    by_key = _players_by_key()
    lineup = _lineup(_legal_assignments(by_key))
    violations = validate_lineup(lineup, by_key, OptimizerSettings(), excluded_keys=["phi_c"])
    assert any("Excluded player" in v for v in violations)


def test_stack_requirement_not_met_detected():
    by_key = _players_by_key()
    # Spread hitters across teams so no single team reaches 5.
    assignments = [
        _assignment("P", by_key["p_tor"]), _assignment("P", by_key["p_pit"]),
        _assignment("C", by_key["phi_c"]), _assignment("1B", by_key["nyy_1b"]),
        _assignment("2B", by_key["bal_2b"]), _assignment("3B", by_key["cin_3b"]),
        _assignment("SS", by_key["cws_ss"]), _assignment("OF", by_key["phi_of1"]),
        _assignment("OF", by_key["nyy_of1"]), _assignment("OF", by_key["conflict_hitter"]),
    ]
    lineup = _lineup(assignments)
    violations = validate_lineup(lineup, by_key, OptimizerSettings(stack_size=5))
    assert any("Stack requirement" in v or "No team meets" in v for v in violations)


def test_pitcher_vs_hitter_conflict_detected():
    by_key = _players_by_key()
    assignments = _legal_assignments(by_key)
    assignments[0] = _assignment("P", by_key["p_tor"])
    assignments[-3] = _assignment("OF", by_key["conflict_hitter"])
    lineup = _lineup(assignments)
    violations = validate_lineup(lineup, by_key, OptimizerSettings(allow_pitcher_vs_hitter=False))
    assert any("shares the lineup" in v for v in violations)


def test_team_max_exceeded_detected():
    by_key = _players_by_key()
    assignments = _legal_assignments(by_key)
    # Swap all 3 OF to PHI hitters (only 2 exist -- use nyy slots -> phi anyway triggers via low cap)
    settings = OptimizerSettings(team_max_hitters=4)
    lineup = _lineup(assignments)  # 5 PHI hitters (C,1B,2B,3B,SS) already exceeds a cap of 4
    violations = validate_lineup(lineup, by_key, settings)
    assert any("exceeds team max" in v for v in violations)


def test_exposure_cap_exceeded_detected_at_set_level():
    by_key = _players_by_key()
    lineup1 = _lineup(_legal_assignments(by_key), index=1)
    lineup2 = _lineup(_legal_assignments(by_key), index=2)  # identical -- both contain phi_c
    violations = validate_lineup_set(
        [lineup1, lineup2], by_key, OptimizerSettings(), max_exposure_caps={"phi_c": 1}, min_unique=0,
    )
    assert any("Exposure cap exceeded" in v for v in violations[1] + violations[2])


def test_uniqueness_violation_detected_at_set_level():
    by_key = _players_by_key()
    lineup1 = _lineup(_legal_assignments(by_key), index=1)
    lineup2 = _lineup(_legal_assignments(by_key), index=2)  # identical lineup, 0 players different
    violations = validate_lineup_set([lineup1, lineup2], by_key, OptimizerSettings(), min_unique=2)
    assert any("differ by only" in v for v in violations[1])
