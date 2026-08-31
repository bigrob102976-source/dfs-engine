"""NFL M3 -- targeted tests for nfl/lineup_validator.py. Validates SLOT
ASSIGNMENTS, not just aggregate base-position counts -- see
test_three_rbs_valid_only_if_one_is_flex below for the specific case
called out in the M3 task."""

from nfl.lineup_validator import validate_lineup
from nfl.optimizer_models import NflLineup, NflLineupSlotAssignment, NflOptimizerPlayer

DG_ID = 151307
DATE = "2026-09-13"


def _p(key, name, position, salary, roster_slots=None):
    return NflOptimizerPlayer(
        key=key, name=name, team="PHI", opponent="DAL", game_id="100", position=position,
        roster_slots=roster_slots or ([position, "FLEX"] if position in ("RB", "WR", "TE") else [position]),
        salary=salary, is_team_entity=(position == "DST"), draft_group_id=DG_ID, slate_date=DATE,
    )


def _valid_pool_and_lineup():
    players = {
        "qb1": _p("qb1", "QB One", "QB", 7000),
        "rb1": _p("rb1", "RB One", "RB", 6000),
        "rb2": _p("rb2", "RB Two", "RB", 5000),
        "rb3": _p("rb3", "RB Three", "RB", 4000),
        "wr1": _p("wr1", "WR One", "WR", 5500),
        "wr2": _p("wr2", "WR Two", "WR", 4500),
        "wr3": _p("wr3", "WR Three", "WR", 4000),
        "te1": _p("te1", "TE One", "TE", 3500),
        "dst1": _p("dst1", "Team DST", "DST", 2500),
    }
    assignments = [
        NflLineupSlotAssignment("QB", "qb1", "QB One", "QB", "PHI", 7000),
        NflLineupSlotAssignment("RB1", "rb1", "RB One", "RB", "PHI", 6000),
        NflLineupSlotAssignment("RB2", "rb2", "RB Two", "RB", "PHI", 5000),
        NflLineupSlotAssignment("WR1", "wr1", "WR One", "WR", "PHI", 5500),
        NflLineupSlotAssignment("WR2", "wr2", "WR Two", "WR", "PHI", 4500),
        NflLineupSlotAssignment("WR3", "wr3", "WR Three", "WR", "PHI", 4000),
        NflLineupSlotAssignment("TE", "te1", "TE One", "TE", "PHI", 3500),
        NflLineupSlotAssignment("FLEX", "rb3", "RB Three", "RB", "PHI", 4000),
        NflLineupSlotAssignment("DST", "dst1", "Team DST", "DST", "PHI", 2500),
    ]
    total = sum(a.salary for a in assignments)
    lineup = NflLineup(index=0, assignments=assignments, total_salary=total, remaining_salary=50000 - total, draft_group_id=DG_ID, slate_date=DATE)
    return players, lineup


def test_valid_lineup_has_no_violations():
    players, lineup = _valid_pool_and_lineup()
    assert validate_lineup(lineup, players) == []


def test_three_rbs_valid_only_if_one_is_flex():
    """3 real RBs (2 base + 1 FLEX) is legal; the SAME 3 RBs with one
    mislabeled as a second RB slot (RB1 filled twice, no real FLEX
    assignment) must be rejected -- an aggregate 'RB count == 3' check
    alone would wrongly accept this."""
    players, lineup = _valid_pool_and_lineup()
    bad_assignments = list(lineup.assignments)
    # Replace the FLEX assignment with a duplicate "RB1" label instead --
    # 3 RBs still present in aggregate, but slot instances are wrong.
    bad_assignments[-2] = NflLineupSlotAssignment("RB1", "rb3", "RB Three", "RB", "PHI", 4000)
    bad_lineup = NflLineup(index=0, assignments=bad_assignments, total_salary=lineup.total_salary, remaining_salary=lineup.remaining_salary, draft_group_id=DG_ID, slate_date=DATE)
    violations = validate_lineup(bad_lineup, players)
    assert any("RB1" in v for v in violations)
    assert any("FLEX" in v for v in violations)


def test_flex_player_not_actually_flex_eligible_is_rejected():
    players, lineup = _valid_pool_and_lineup()
    # A QB can never legally occupy FLEX -- construct that directly.
    players["qb2"] = _p("qb2", "QB Two", "QB", 4000)
    bad_assignments = list(lineup.assignments)
    bad_assignments[-2] = NflLineupSlotAssignment("FLEX", "qb2", "QB Two", "QB", "PHI", 4000)
    bad_lineup = NflLineup(index=0, assignments=bad_assignments, total_salary=lineup.total_salary, remaining_salary=lineup.remaining_salary, draft_group_id=DG_ID, slate_date=DATE)
    violations = validate_lineup(bad_lineup, players)
    assert any("not eligible for 'FLEX'" in v for v in violations)


def test_wrong_roster_size_is_rejected():
    players, lineup = _valid_pool_and_lineup()
    short_lineup = NflLineup(index=0, assignments=lineup.assignments[:8], total_salary=lineup.total_salary, remaining_salary=lineup.remaining_salary, draft_group_id=DG_ID, slate_date=DATE)
    violations = validate_lineup(short_lineup, players)
    assert any("Roster size is 8" in v for v in violations)


def test_duplicate_player_is_rejected():
    players, lineup = _valid_pool_and_lineup()
    bad_assignments = list(lineup.assignments)
    bad_assignments[-1] = NflLineupSlotAssignment("DST", "qb1", "QB One", "QB", "PHI", 7000)  # qb1 reused instead of dst1
    bad_lineup = NflLineup(index=0, assignments=bad_assignments, total_salary=lineup.total_salary, remaining_salary=lineup.remaining_salary, draft_group_id=DG_ID, slate_date=DATE)
    violations = validate_lineup(bad_lineup, players)
    assert any("Duplicate player ID" in v for v in violations)


def test_salary_over_cap_is_rejected():
    players, lineup = _valid_pool_and_lineup()
    over_cap_lineup = NflLineup(index=0, assignments=lineup.assignments, total_salary=60000, remaining_salary=-10000, draft_group_id=DG_ID, slate_date=DATE)
    violations = validate_lineup(over_cap_lineup, players, salary_cap=50000)
    assert any("exceeds the salary cap" in v for v in violations)


def test_missing_lock_is_rejected():
    players, lineup = _valid_pool_and_lineup()
    violations = validate_lineup(lineup, players, locked_keys=["does-not-exist"])
    assert any("Locked player(s) missing" in v for v in violations)


def test_present_exclude_is_rejected():
    players, lineup = _valid_pool_and_lineup()
    violations = validate_lineup(lineup, players, excluded_keys=["qb1"])
    assert any("Excluded player(s) present" in v for v in violations)


def test_wrong_mode_is_rejected():
    players, lineup = _valid_pool_and_lineup()
    lineup.mode = "not_roster_feasibility"
    violations = validate_lineup(lineup, players)
    assert any("expected 'roster_feasibility'" in v for v in violations)
