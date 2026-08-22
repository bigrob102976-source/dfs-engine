"""Milestone 32.2B -- structural validation tests for the DraftKings
unofficial provider's Classic-slate check
(draftkings_unofficial/structural_validation.py). All fixtures are
synthetic; no network calls."""

from draftkings_unofficial.models import DkContest, DkDraftable, DkRosterRules, DkRosterSlot, DkSlateGame, DkTeam
from draftkings_unofficial.structural_validation import BLOCK, WARN, validate_classic_draftgroup

DG_ID = 152543


def _contest(game_type="Classic"):
    return DkContest(
        contest_id=1, name="MLB $150K Walk-Off Home Run", sport_id=2, draft_group_id=DG_ID,
        game_type=game_type, game_type_id=2, start_time_raw=None, start_time_iso=None,
    )


def _game(competition_id=100, home="BOS", away="TOR"):
    return DkSlateGame(
        competition_id=competition_id, sport_id=2, name=f"{away} @ {home}", start_time="2026-08-22T23:05:00Z",
        home_team=DkTeam(team_id=1, abbreviation=home), away_team=DkTeam(team_id=2, abbreviation=away),
    )


def _valid_roster_slots():
    names = ["P", "P", "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF"]
    return [DkRosterSlot(roster_slot_id=110 + i, name=n) for i, n in enumerate(names)]


def _rules(salary_cap=50000, salary_cap_enabled=True, slots=None):
    return DkRosterRules(
        game_type_id=2, sport_id=2, name="Classic", draft_type="SalaryCap",
        salary_cap_enabled=salary_cap_enabled, salary_cap=salary_cap,
        roster_slots=_valid_roster_slots() if slots is None else slots,
    )


def _draftable(player_id, name, team, position, roster_slot_id, competition_id=100, salary=5000, draftable_id=None):
    return DkDraftable(
        draftable_id=draftable_id or (player_id * 10 + roster_slot_id), draft_group_id=DG_ID,
        player_id=player_id, player_dk_id=player_id, display_name=name, first_name=None, last_name=None,
        position=position, roster_slot_id=roster_slot_id, salary=salary, status="None",
        team_id=1, team_abbreviation=team, competition_id=competition_id,
    )


def _valid_minimal_slate():
    games = [_game()]
    draftables = [
        _draftable(1, "Ace Pitcher", "BOS", "SP", 110),
        _draftable(2, "Setup Man", "TOR", "RP", 110),
        _draftable(3, "Flex Player", "BOS", "1B", 112),
    ]
    return games, draftables


def test_valid_classic_draftgroup_passes():
    games, draftables = _valid_minimal_slate()
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert result.passed is True
    assert result.findings == []


def test_raw_draftable_count_vs_unique_player_count_distinction():
    games = [_game()]
    draftables = [
        _draftable(1, "Flex Player", "BOS", "1B", 112, draftable_id=1001),
        _draftable(1, "Flex Player", "BOS", "OF", 116, draftable_id=1002),  # same player_id, different roster slot
        _draftable(2, "Ace Pitcher", "TOR", "SP", 110, draftable_id=1003),
    ]
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert result.raw_draftable_count == 3
    assert result.unique_player_count == 2
    assert result.passed is True  # multi-slot dupe explained by different roster_slot_id -- not a finding


def test_multi_slot_duplicate_in_same_roster_slot_blocks():
    """A genuine duplicate row -- same player_id AND same roster_slot_id
    -- is NOT explainable by roster-slot eligibility."""
    games = [_game()]
    draftables = [
        _draftable(1, "Flex Player", "BOS", "1B", 112, draftable_id=1001),
        _draftable(1, "Flex Player", "BOS", "1B", 112, draftable_id=1002),  # true duplicate, same slot
    ]
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "SAME roster slot" in f.message for f in result.findings)


def test_wrong_game_type_blocks():
    games, draftables = _valid_minimal_slate()
    result = validate_classic_draftgroup(DG_ID, [_contest(game_type="Showdown Captain Mode")], games, draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "Classic" in f.message for f in result.findings)


def test_invalid_roster_template_blocks():
    games, draftables = _valid_minimal_slate()
    bad_slots = [DkRosterSlot(roster_slot_id=1, name="CPT"), DkRosterSlot(roster_slot_id=2, name="FLEX")]
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules(slots=bad_slots))
    assert result.passed is False
    assert any(f.level == BLOCK and "Roster template" in f.message for f in result.findings)


def test_salary_cap_disabled_blocks():
    games, draftables = _valid_minimal_slate()
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules(salary_cap_enabled=False))
    assert result.passed is False
    assert any(f.level == BLOCK and "Salary cap is not enabled" in f.message for f in result.findings)


def test_missing_salary_cap_blocks():
    games, draftables = _valid_minimal_slate()
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules(salary_cap=None))
    assert result.passed is False
    assert any(f.level == BLOCK and "Implausible or missing salary cap" in f.message for f in result.findings)


def test_missing_roster_rules_blocks():
    games, draftables = _valid_minimal_slate()
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, None)
    assert result.passed is False
    assert any(f.level == BLOCK and "No roster/salary-cap rules" in f.message for f in result.findings)


def test_no_games_blocks():
    _, draftables = _valid_minimal_slate()
    result = validate_classic_draftgroup(DG_ID, [_contest()], [], draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "No games found" in f.message for f in result.findings)


def test_player_assigned_to_a_game_they_are_not_in_blocks():
    games = [_game(competition_id=100, home="BOS", away="TOR")]
    draftables = [
        _draftable(1, "Ace Pitcher", "BOS", "SP", 110, competition_id=100),
        _draftable(2, "Wrong Team Guy", "NYY", "SP", 110, competition_id=100),  # NYY not in this game
    ]
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "aren't actually scheduled" in f.message for f in result.findings)


def test_player_referencing_unknown_competition_blocks():
    games = [_game(competition_id=100)]
    draftables = [_draftable(1, "Ghost Player", "BOS", "SP", 110, competition_id=999)]
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "aren't actually scheduled" in f.message for f in result.findings)


def test_unrecognized_position_string_warns_not_blocks():
    games, draftables = _valid_minimal_slate()
    draftables.append(_draftable(4, "Weird Position Guy", "BOS", "DST", 999, draftable_id=9999))
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert any(f.level == WARN and "unrecognized position" in f.message.lower() for f in result.findings)
    assert result.passed is True  # WARN only -- must not block


def test_nonpositive_salary_warns_not_blocks():
    games, draftables = _valid_minimal_slate()
    draftables.append(_draftable(4, "Zero Salary Guy", "BOS", "OF", 116, draftable_id=9999, salary=0))
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert any(f.level == WARN and "non-positive salary" in f.message for f in result.findings)
    assert result.passed is True


def test_team_count_not_matching_two_per_game_warns_not_blocks():
    games = [_game(competition_id=100), _game(competition_id=200, home="LAD", away="SF")]
    draftables = [_draftable(1, "Ace Pitcher", "BOS", "SP", 110, competition_id=100)]  # only 1 team represented, expected 4
    result = validate_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert any(f.level == WARN and "distinct team" in f.message for f in result.findings)
    assert result.passed is True
