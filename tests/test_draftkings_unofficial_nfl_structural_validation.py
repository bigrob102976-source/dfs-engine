"""NFL M1 -- structural validation tests for the DraftKings unofficial
provider's NFL Classic-slate check
(draftkings_unofficial/structural_validation.py::validate_nfl_classic_
draftgroup()). All fixtures are synthetic; no network calls.

Mirrors tests/test_draftkings_unofficial_structural_validation.py's
fixture pattern exactly -- this only needs to prove the NFL-specific
wrapper and its constants are wired correctly, since the underlying
check engine itself is already covered by that file's MLB tests (the
same shared _validate_draftgroup_structure() runs either way)."""

from draftkings_unofficial.models import DkContest, DkDraftable, DkRosterRules, DkRosterSlot, DkSlateGame, DkTeam
from draftkings_unofficial.structural_validation import BLOCK, validate_nfl_classic_draftgroup

DG_ID = 151307


def _contest(game_type="Classic", game_type_id=1):
    return DkContest(
        contest_id=1, name="NFL $1M Sunday Million", sport_id=1, draft_group_id=DG_ID,
        game_type=game_type, game_type_id=game_type_id, start_time_raw=None, start_time_iso=None,
    )


def _game(competition_id=100, home="PHI", away="DAL"):
    return DkSlateGame(
        competition_id=competition_id, sport_id=1, name=f"{away} @ {home}", start_time="2026-09-13T17:00:00Z",
        home_team=DkTeam(team_id=1, abbreviation=home), away_team=DkTeam(team_id=2, abbreviation=away),
    )


def _valid_nfl_roster_slots():
    # Verified LIVE against DraftGroup 151307's real
    # /lineups/v1/gametypes/1/rules response.
    names = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
    return [DkRosterSlot(roster_slot_id=60 + i, name=n) for i, n in enumerate(names)]


def _rules(salary_cap=50000, salary_cap_enabled=True, slots=None):
    return DkRosterRules(
        game_type_id=1, sport_id=1, name="Classic", draft_type="SalaryCap",
        salary_cap_enabled=salary_cap_enabled, salary_cap=salary_cap,
        roster_slots=_valid_nfl_roster_slots() if slots is None else slots,
    )


def _draftable(player_id, name, team, position, roster_slot_id, competition_id=100, salary=6000, draftable_id=None):
    return DkDraftable(
        draftable_id=draftable_id or (player_id * 10 + roster_slot_id), draft_group_id=DG_ID,
        player_id=player_id, player_dk_id=player_id, display_name=name, first_name=None, last_name=None,
        position=position, roster_slot_id=roster_slot_id, salary=salary, status="None",
        team_id=1, team_abbreviation=team, competition_id=competition_id,
    )


def _valid_minimal_slate():
    games = [_game()]
    draftables = [
        _draftable(1, "Starting QB", "PHI", "QB", 60, salary=7500),
        _draftable(2, "Starting RB", "DAL", "RB", 61, salary=6500),
        _draftable(3, "Starting WR", "PHI", "WR", 63, salary=5500),
        _draftable(4, "Starting DST", "DAL", "DST", 68, salary=2500),
    ]
    return games, draftables


def test_valid_nfl_classic_draftgroup_passes():
    games, draftables = _valid_minimal_slate()
    result = validate_nfl_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules())
    assert result.passed is True
    assert result.findings == []


def test_showdown_captain_mode_blocks():
    """Real DK Showdown Captain Mode reports gameTypeName "Showdown
    Captain Mode", not "Classic" -- rejected by the game-type check
    alone, with no NFL-specific carve-out needed."""
    games, draftables = _valid_minimal_slate()
    result = validate_nfl_classic_draftgroup(DG_ID, [_contest(game_type="Showdown Captain Mode", game_type_id=96)], games, draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "Classic" in f.message for f in result.findings)


def test_madden_stream_blocks():
    """Real DK "Madden Stream"/"Madden Classic" esports contests report
    gameTypeName "Madden Classic" (or similar) -- never real NFL player
    data, correctly rejected by the same game-type check."""
    games, draftables = _valid_minimal_slate()
    result = validate_nfl_classic_draftgroup(DG_ID, [_contest(game_type="Madden Classic", game_type_id=158)], games, draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "Classic" in f.message for f in result.findings)


def test_best_ball_blocks():
    """Real DK Best Ball reports gameTypeName "Best Ball" and has salary
    cap disabled entirely -- both independently BLOCK."""
    games, draftables = _valid_minimal_slate()
    rules = _rules(salary_cap_enabled=False, salary_cap=None)
    result = validate_nfl_classic_draftgroup(DG_ID, [_contest(game_type="Best Ball", game_type_id=145)], games, draftables, rules)
    assert result.passed is False
    assert any(f.level == BLOCK and "Classic" in f.message for f in result.findings)
    assert any(f.level == BLOCK and "Salary cap is not enabled" in f.message for f in result.findings)


def test_wrong_roster_template_blocks():
    """A Showdown-shaped roster (CPT/FLEX) does not match the expected
    NFL Classic template (QB/RB/RB/WR/WR/WR/TE/FLEX/DST)."""
    games, draftables = _valid_minimal_slate()
    bad_slots = [DkRosterSlot(roster_slot_id=1, name="CPT")] + [DkRosterSlot(roster_slot_id=2 + i, name="FLEX") for i in range(5)]
    result = validate_nfl_classic_draftgroup(DG_ID, [_contest()], games, draftables, _rules(slots=bad_slots))
    assert result.passed is False
    assert any(f.level == BLOCK and "Roster template" in f.message for f in result.findings)


def test_missing_roster_rules_blocks():
    games, draftables = _valid_minimal_slate()
    result = validate_nfl_classic_draftgroup(DG_ID, [_contest()], games, draftables, None)
    assert result.passed is False
    assert any(f.level == BLOCK and "No roster/salary-cap rules" in f.message for f in result.findings)


def test_no_games_blocks():
    _, draftables = _valid_minimal_slate()
    result = validate_nfl_classic_draftgroup(DG_ID, [_contest()], [], draftables, _rules())
    assert result.passed is False
    assert any(f.level == BLOCK and "No games found" in f.message for f in result.findings)
