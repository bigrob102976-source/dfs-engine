from draftkings_unofficial.models import DkContest, DkDraftable, DkSlate, DkSlateGame, PlayerIdentityMatch
from draftkings_unofficial.quality import build_quality_report


def _draftable(draftable_id, player_id=1, team_id=1, salary=4000, position="OF"):
    return DkDraftable(
        draftable_id=draftable_id, draft_group_id=1, player_id=player_id, player_dk_id=player_id,
        display_name=f"P{draftable_id}", first_name=None, last_name=None, position=position, roster_slot_id=1,
        salary=salary, status="None", team_id=team_id, team_abbreviation="BOS", competition_id=1,
    )


def _contest(contest_id, start_time_iso="2026-08-20T18:00:00+00:00"):
    return DkContest(contest_id=contest_id, name="X", sport_id=2, draft_group_id=1, game_type="Classic",
                      game_type_id=2, start_time_raw="x", start_time_iso=start_time_iso)


def _slate(draft_group_id, games):
    return DkSlate(draft_group_id=draft_group_id, sport_id=2, sport_code="MLB", game_type_id=2, game_type_name="Classic",
                    start_time="x", games=games)


def _game(competition_id):
    return DkSlateGame(competition_id=competition_id, sport_id=2, name="X", start_time="x")


def test_basic_counts():
    draftables = [_draftable(1), _draftable(2)]
    slates = [_slate(1, [_game(100)])]
    report = build_quality_report(25, [_contest(1)], slates, draftables, [])
    assert report["sports_discovered"] == 25
    assert report["contests_discovered"] == 1
    assert report["unique_draft_groups"] == 1
    assert report["games"] == 1
    assert report["draftables"] == 2


def test_salary_coverage_percent():
    draftables = [_draftable(1, salary=4000), _draftable(2, salary=None)]
    report = build_quality_report(1, [], [], draftables, [])
    assert report["salary_coverage_percent"] == 50.0
    assert report["invalid_salaries"] == 1


def test_position_coverage_percent():
    draftables = [_draftable(1, position="OF"), _draftable(2, position=None)]
    report = build_quality_report(1, [], [], draftables, [])
    assert report["position_coverage_percent"] == 50.0


def test_duplicate_draftable_ids_detected():
    draftables = [_draftable(1), _draftable(1)]
    report = build_quality_report(1, [], [], draftables, [])
    assert report["duplicate_draftable_ids"] == 1


def test_missing_player_and_team_ids_detected():
    draftables = [_draftable(1, player_id=None, team_id=None)]
    report = build_quality_report(1, [], [], draftables, [])
    assert report["missing_player_ids"] == 1
    assert report["missing_team_ids"] == 1


def test_invalid_contest_start_times_detected():
    report = build_quality_report(1, [_contest(1, start_time_iso=None)], [], [], [])
    assert report["invalid_contest_start_times"] == 1


def test_unresolved_identities_counted():
    matches = [
        PlayerIdentityMatch(draftable_id=1, provider_player_id=1, display_name="A", sport_code="MLB", match_status="matched"),
        PlayerIdentityMatch(draftable_id=2, provider_player_id=2, display_name="B", sport_code="MLB", match_status="unmatched"),
        PlayerIdentityMatch(draftable_id=3, provider_player_id=3, display_name="C", sport_code="MLB", match_status="ambiguous"),
    ]
    report = build_quality_report(1, [], [], [], matches)
    assert report["unresolved_identities"] == 2


def test_unique_players_deduplicated_by_player_id():
    draftables = [_draftable(1, player_id=100), _draftable(2, player_id=100), _draftable(3, player_id=200)]
    report = build_quality_report(1, [], [], draftables, [])
    assert report["unique_players"] == 2


def test_empty_inputs_never_crash():
    report = build_quality_report(0, [], [], [], [])
    assert report["draftables"] == 0
    assert report["salary_coverage_percent"] == 0.0
    assert report["position_coverage_percent"] == 0.0
