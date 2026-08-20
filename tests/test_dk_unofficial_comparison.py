from dfs.models import DKSalaryRow
from draftkings_unofficial.comparison import compare_csv_to_api
from draftkings_unofficial.models import DkDraftable


def _csv_row(dk_id, name, team, salary, positions, game_info="TOR@BOS 7:05PM ET"):
    return DKSalaryRow(dk_player_id=dk_id, name=name, team_abbrev=team, dk_positions=positions, salary=salary, game_info=game_info)


def _api_draftable(draftable_id, player_dk_id, name, team, salary, position, competition_id=1):
    return DkDraftable(
        draftable_id=draftable_id, draft_group_id=1, player_id=player_dk_id, player_dk_id=player_dk_id,
        display_name=name, first_name=None, last_name=None, position=position, roster_slot_id=1,
        salary=salary, status="None", team_id=1, team_abbreviation=team, competition_id=competition_id,
    )


def test_matches_by_dk_id_when_ids_agree():
    csv_rows = [_csv_row("873630", "Cam Schlittler", "NYY", 11000, ["P"])]
    api = [_api_draftable(1, 873630, "Cam Schlittler", "NYY", 11000, "SP")]
    result = compare_csv_to_api(csv_rows, api)
    assert result.matched_players == 1
    assert result.matched_by_id == 1
    assert result.matched_by_name_team == 0
    assert result.exact_salary_matches == 1


def test_falls_back_to_name_team_when_ids_disagree():
    csv_rows = [_csv_row("99999999", "Cam Schlittler", "NYY", 11000, ["P"])]
    api = [_api_draftable(1, 873630, "Cam Schlittler", "NYY", 11000, "SP")]
    result = compare_csv_to_api(csv_rows, api)
    assert result.matched_players == 1
    assert result.matched_by_id == 0
    assert result.matched_by_name_team == 1


def test_salary_mismatch_reported():
    csv_rows = [_csv_row("1", "Player X", "NYY", 5000, ["OF"])]
    api = [_api_draftable(1, 1, "Player X", "NYY", 5200, "OF")]
    result = compare_csv_to_api(csv_rows, api)
    assert result.exact_salary_matches == 0
    assert len(result.salary_mismatches) == 1
    assert result.salary_mismatches[0].csv_salary == 5000
    assert result.salary_mismatches[0].api_salary == 5200


def test_position_mismatch_reported():
    csv_rows = [_csv_row("1", "Player X", "NYY", 5000, ["1B"])]
    api = [_api_draftable(1, 1, "Player X", "NYY", 5000, "OF")]
    result = compare_csv_to_api(csv_rows, api)
    assert result.position_matches == 0
    assert len(result.position_mismatches) == 1


def test_position_matches_when_api_position_is_one_of_csv_multi_positions():
    csv_rows = [_csv_row("1", "Player X", "NYY", 5000, ["1B", "OF"])]
    api = [_api_draftable(1, 1, "Player X", "NYY", 5000, "OF")]
    result = compare_csv_to_api(csv_rows, api)
    assert result.position_matches == 1


def test_position_matches_when_api_reports_slash_joined_multi_position():
    # The Draftables API can itself report a multi-position player as one
    # slash-joined string (e.g. "2B/3B"), not split into a list like the
    # CSV's own dk_positions -- confirmed live during this milestone's
    # audit. Splitting both sides the same way must not falsely flag a
    # real multi-position player as a mismatch.
    csv_rows = [_csv_row("1", "Player X", "HOU", 5000, ["2B", "3B"])]
    api = [_api_draftable(1, 1, "Player X", "HOU", 5000, "2B/3B")]
    result = compare_csv_to_api(csv_rows, api)
    assert result.position_matches == 1
    assert result.position_mismatches == []


def test_csv_only_player_reported():
    csv_rows = [_csv_row("1", "CSV Only Guy", "NYY", 5000, ["OF"])]
    result = compare_csv_to_api(csv_rows, [])
    assert result.csv_only == ["CSV Only Guy (NYY)"]
    assert result.matched_players == 0


def test_api_only_player_reported():
    api = [_api_draftable(1, 1, "API Only Guy", "NYY", 5000, "OF")]
    result = compare_csv_to_api([], api)
    assert result.api_only == ["API Only Guy (NYY)"]


def test_counts_reflect_full_rows():
    csv_rows = [_csv_row("1", "A", "NYY", 5000, ["OF"]), _csv_row("2", "B", "NYY", 5000, ["OF"])]
    api = [_api_draftable(1, 1, "A", "NYY", 5000, "OF")]
    result = compare_csv_to_api(csv_rows, api)
    assert result.csv_rows == 2
    assert result.api_rows == 1


def test_never_mutates_inputs():
    csv_rows = [_csv_row("1", "A", "NYY", 5000, ["OF"])]
    api = [_api_draftable(1, 1, "A", "NYY", 5200, "OF")]
    compare_csv_to_api(csv_rows, api)
    assert csv_rows[0].salary == 5000
    assert api[0].salary == 5200


def test_to_dict_serializes_mismatches():
    csv_rows = [_csv_row("1", "A", "NYY", 5000, ["OF"])]
    api = [_api_draftable(1, 1, "A", "NYY", 5200, "OF")]
    result = compare_csv_to_api(csv_rows, api)
    d = result.to_dict()
    assert d["salary_mismatches"][0]["csv_salary"] == 5000
