from draftkings_unofficial import schema_guard


def test_check_sports_ok():
    result = schema_guard.check_sports({"sports": []})
    assert result.ok
    assert result.missing_keys == []


def test_check_sports_schema_changed():
    result = schema_guard.check_sports({"somethingElse": []})
    assert not result.ok
    assert result.missing_keys == ["sports"]
    assert result.observed_keys == ["somethingElse"]
    assert result.sample is not None


def test_check_non_dict_payload_is_schema_changed():
    result = schema_guard.check("sports", ["not", "a", "dict"], ["sports"])
    assert not result.ok
    assert result.observed_keys == []


def test_check_contests_requires_all_three_top_level_keys():
    result = schema_guard.check_contests({"Contests": [], "DraftGroups": []})  # missing GameTypes
    assert not result.ok
    assert "GameTypes" in result.missing_keys


def test_check_draftables_ok():
    result = schema_guard.check_draftables({"draftables": [], "competitions": []})
    assert result.ok


def test_check_game_type_rules_ok():
    result = schema_guard.check_game_type_rules({"gameTypeId": 2, "lineupTemplate": [], "salaryCap": {}})
    assert result.ok


def test_check_contest_details_ok():
    result = schema_guard.check_contest_details({"contestDetail": {}})
    assert result.ok


def test_check_record_reports_missing_record_level_keys():
    result = schema_guard.check_record("sports.sport", {"sportId": 2}, schema_guard.EXPECTED_SPORT_KEYS)
    assert not result.ok
    assert "regionAbbreviatedSportName" in result.missing_keys


def test_to_dict_reports_schema_changed_status_string():
    result = schema_guard.check_sports({})
    d = result.to_dict()
    assert d["status"] == "SCHEMA_CHANGED"
    assert d["endpoint"] == "sports"


def test_to_dict_reports_ok_status_string():
    result = schema_guard.check_sports({"sports": []})
    assert result.to_dict()["status"] == "ok"


def test_sample_is_length_capped():
    huge_payload = {"x": "y" * 10000}
    result = schema_guard.check("x", huge_payload, ["not_present"])
    assert len(result.sample) <= 500
