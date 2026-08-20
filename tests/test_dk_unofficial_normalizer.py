"""Normalizer tests for the unofficial DraftKings provider. Fixtures
are trimmed, structurally faithful copies of REAL live responses
captured during Milestone 31.2's discovery pass (2026-08-20) -- not
guessed shapes."""

from draftkings_unofficial.normalizer import (
    normalize_contests,
    normalize_draft_groups_to_slates,
    normalize_draftables,
    normalize_game_type_rules,
    normalize_game_types,
    normalize_sports,
    _parse_dotnet_date,
    _parse_multiplier,
)

# ----------------------------------------------------------------------------
# Sports
# ----------------------------------------------------------------------------

SPORTS_PAYLOAD = {
    "sports": [
        {"sportId": 2, "fullName": "Baseball", "sortOrder": 1, "hasPublicContests": True, "isEnabled": True,
         "regionFullSportName": "Baseball", "regionAbbreviatedSportName": "MLB"},
        {"sportId": 3, "fullName": "Hockey", "sortOrder": 7, "hasPublicContests": False, "isEnabled": True,
         "regionFullSportName": "Hockey", "regionAbbreviatedSportName": "NHL"},
    ]
}


def test_normalize_sports_parses_real_shape():
    sports, skipped, check = normalize_sports(SPORTS_PAYLOAD)
    assert check.ok
    assert len(sports) == 2
    assert sports[0].sport_id == 2
    assert sports[0].code == "MLB"
    assert sports[0].has_public_contests is True
    assert sports[1].code == "NHL"
    assert sports[1].has_public_contests is False
    assert skipped == []


def test_normalize_sports_schema_changed_when_top_level_key_missing():
    sports, skipped, check = normalize_sports({"unexpected": []})
    assert not check.ok
    assert sports == []
    assert "sports" in check.missing_keys


def test_normalize_sports_skips_malformed_individual_record_without_crashing():
    payload = {"sports": [
        {"sportId": 2, "fullName": "Baseball", "hasPublicContests": True, "isEnabled": True, "regionAbbreviatedSportName": "MLB"},
        {"sportId": 99},  # missing required fields
    ]}
    sports, skipped, check = normalize_sports(payload)
    assert check.ok  # top-level shape is fine
    assert len(sports) == 1
    assert len(skipped) == 1
    assert skipped[0]["raw"]["sportId"] == 99


def test_normalize_sports_empty_list_returns_empty_not_error():
    sports, skipped, check = normalize_sports({"sports": []})
    assert check.ok
    assert sports == []


# ----------------------------------------------------------------------------
# Contests / GameTypes / DraftGroups -> Slates
# ----------------------------------------------------------------------------

CONTESTS_PAYLOAD = {
    "SelectedSport": "MLB",
    "Contests": [
        {
            "id": 190035665, "n": "MLB $4M Ultimate Main Event [$1M to 1st]", "s": 2, "dg": 152389,
            "gameType": "Classic", "gameTypeId": 2, "sd": "/Date(1788306000000)/", "po": 4002000.0,
            "m": 1334, "a": 3333, "mec": 40, "fpp": 0,
            "attr": {"IsGuaranteed": "true", "IsStarred": "true"},
        },
        {
            "id": 190035666, "n": "MLB Showdown Single Game", "s": 2, "dg": 152391,
            "gameType": "Showdown Captain Mode", "gameTypeId": 114, "sd": "/Date(1788306000000)/", "po": 500.0,
            "m": 100, "a": 20, "mec": 3, "fpp": 5,
            "attr": {},
        },
    ],
    "DraftGroups": [
        {"DraftGroupId": 152389, "SportId": 2, "Sport": "MLB", "GameTypeId": 2, "GameType": None,
         "StartDate": "2026-08-20T22:35:00.0000000Z", "StartDateEst": "2026-08-20T18:35:00.0000000",
         "DraftGroupTag": "Featured", "ContestStartTimeSuffix": " (Night)", "GameCount": 3},
        {"DraftGroupId": 152391, "SportId": 2, "Sport": "MLB", "GameTypeId": 114, "GameType": None,
         "StartDate": "2026-08-20T22:35:00.0000000Z", "StartDateEst": "2026-08-20T18:35:00.0000000",
         "DraftGroupTag": "", "ContestStartTimeSuffix": " (NYY @ BAL)", "GameCount": 1},
    ],
    "GameTypes": [
        {"GameTypeId": 2, "Name": "Classic", "Description": "Create a 10-player lineup", "SportId": 2, "DraftType": "SalaryCap", "IsSeasonLong": False},
        {"GameTypeId": 114, "Name": "Showdown Captain Mode", "Description": "1 game", "SportId": 2, "DraftType": "SalaryCap", "IsSeasonLong": False},
    ],
}


def test_normalize_contests_parses_real_shape():
    contests, skipped, check = normalize_contests(CONTESTS_PAYLOAD)
    assert check.ok
    assert len(contests) == 2
    c = contests[0]
    assert c.contest_id == 190035665
    assert c.name == "MLB $4M Ultimate Main Event [$1M to 1st]"
    assert c.draft_group_id == 152389
    assert c.game_type_id == 2
    assert c.prize_pool == 4002000.0
    assert c.is_guaranteed is True
    assert c.is_starred is True
    assert c.start_time_raw == "/Date(1788306000000)/"
    assert c.start_time_iso == "2026-09-01T23:40:00+00:00"


def test_normalize_contests_second_contest_not_starred_not_guaranteed():
    contests, _, _ = normalize_contests(CONTESTS_PAYLOAD)
    assert contests[1].is_guaranteed is False
    assert contests[1].is_starred is False


def test_normalize_contests_schema_changed_when_contests_key_missing():
    contests, skipped, check = normalize_contests({"DraftGroups": [], "GameTypes": []})
    assert not check.ok
    assert contests == []


def test_normalize_game_types():
    game_types, skipped = normalize_game_types(CONTESTS_PAYLOAD)
    assert len(game_types) == 2
    assert game_types[0].name == "Classic"
    assert game_types[1].name == "Showdown Captain Mode"
    assert skipped == []


def test_normalize_draft_groups_to_slates_dedup_and_contest_relationship():
    contests, _, _ = normalize_contests(CONTESTS_PAYLOAD)
    slates, skipped = normalize_draft_groups_to_slates(CONTESTS_PAYLOAD, contests)
    assert len(slates) == 2
    classic_slate = next(s for s in slates if s.draft_group_id == 152389)
    assert classic_slate.contest_ids == [190035665]
    assert classic_slate.tag == "Featured"
    assert classic_slate.label == " (Night)"
    showdown_slate = next(s for s in slates if s.draft_group_id == 152391)
    assert showdown_slate.contest_ids == [190035666]
    assert showdown_slate.label == " (NYY @ BAL)"
    assert skipped == []


def test_normalize_draft_groups_to_slates_multiple_contests_share_one_draftgroup():
    payload = dict(CONTESTS_PAYLOAD)
    payload["Contests"] = list(CONTESTS_PAYLOAD["Contests"]) + [
        {"id": 99999, "n": "Another contest, same DraftGroup", "s": 2, "dg": 152389, "gameType": "Classic",
         "gameTypeId": 2, "sd": "/Date(1788306000000)/", "po": 10.0, "m": 10, "a": 1, "mec": 1, "fpp": 1, "attr": {}},
    ]
    contests, _, _ = normalize_contests(payload)
    slates, _ = normalize_draft_groups_to_slates(payload, contests)
    classic_slate = next(s for s in slates if s.draft_group_id == 152389)
    assert sorted(classic_slate.contest_ids) == [99999, 190035665]  # deduplicated into ONE slate, both contests retained


def test_normalize_draft_groups_skips_malformed_record():
    payload = {"SelectedSport": "MLB", "DraftGroups": [{"DraftGroupId": 1}]}  # missing SportId/GameTypeId
    slates, skipped = normalize_draft_groups_to_slates(payload, [])
    assert slates == []
    assert len(skipped) == 1


# ----------------------------------------------------------------------------
# Draftables (Classic hitter/pitcher, Showdown CPT/UTIL, NASCAR driver)
# ----------------------------------------------------------------------------

DRAFTABLES_CLASSIC_PAYLOAD = {
    "draftables": [
        {
            "draftableId": 43878330, "firstName": "Cam", "lastName": "Schlittler", "displayName": "Cam Schlittler",
            "playerId": 1397686, "playerDkId": 873630, "position": "SP", "rosterSlotId": 110, "salary": 11000,
            "status": "None", "isSwappable": True, "isDisabled": False, "newsStatus": "Breaking",
            "competition": {"competitionId": 6157401, "name": "NYY @ BAL"},
            "teamId": 234, "teamAbbreviation": "NYY",
            "draftStatAttributes": [{"id": 408, "value": "22.9", "sortValue": "22.9"}],
        },
        {
            "draftableId": 43878331, "firstName": "Gunnar", "lastName": "Henderson", "displayName": "Gunnar Henderson",
            "playerId": 2000001, "playerDkId": 900001, "position": "SS", "rosterSlotId": 115, "salary": 5800,
            "status": "None", "isSwappable": True, "isDisabled": False, "newsStatus": None,
            "competition": {"competitionId": 6157401, "name": "NYY @ BAL"},
            "teamId": 225, "teamAbbreviation": "BAL",
        },
    ],
    "competitions": [
        {
            "competitionId": 6157401, "sport": "MLB", "sportId": 2,
            "homeTeam": {"teamId": 225, "teamName": "Orioles", "abbreviation": "BAL", "city": "Baltimore"},
            "awayTeam": {"teamId": 234, "teamName": "Yankees", "abbreviation": "NYY", "city": "New York"},
            "startTime": "2026-08-20T22:35:00.0000000Z", "name": "NYY @ BAL", "venue": "Oriole Park at Camden Yards",
            "competitionState": "Upcoming",
        },
    ],
}


def test_normalize_draftables_classic_shape():
    games, draftables, skipped, check = normalize_draftables(DRAFTABLES_CLASSIC_PAYLOAD, draft_group_id=152389)
    assert check.ok
    assert len(games) == 1
    g = games[0]
    assert g.competition_id == 6157401
    assert g.home_team.abbreviation == "BAL"
    assert g.away_team.abbreviation == "NYY"
    assert g.venue == "Oriole Park at Camden Yards"

    assert len(draftables) == 2
    pitcher = draftables[0]
    assert pitcher.draftable_id == 43878330
    assert pitcher.draft_group_id == 152389
    assert pitcher.display_name == "Cam Schlittler"
    assert pitcher.position == "SP"
    assert pitcher.salary == 11000
    assert pitcher.competition_id == 6157401
    # fppg is deliberately never guessed from unlabeled draftStatAttributes
    assert pitcher.fppg is None
    assert pitcher.raw["draftStatAttributes"][0]["id"] == 408  # raw preserved verbatim
    assert skipped == []


def test_normalize_draftables_schema_changed_when_top_level_missing():
    games, draftables, skipped, check = normalize_draftables({"unexpected": []}, draft_group_id=1)
    assert not check.ok
    assert games == draftables == []


def test_normalize_draftables_skips_malformed_record():
    payload = {"draftables": [{"draftableId": 1}], "competitions": []}  # missing displayName/position/salary/teamId
    games, draftables, skipped, check = normalize_draftables(payload, draft_group_id=1)
    assert check.ok
    assert draftables == []
    assert len(skipped) == 1


def test_normalize_draftables_duplicate_draftable_ids_both_preserved():
    payload = {
        "draftables": [
            {"draftableId": 1, "displayName": "A", "position": "OF", "salary": 4000, "teamId": 1},
            {"draftableId": 1, "displayName": "A", "position": "OF", "salary": 4000, "teamId": 1},
        ],
        "competitions": [],
    }
    _, draftables, _, check = normalize_draftables(payload, draft_group_id=1)
    assert check.ok
    assert len(draftables) == 2  # never silently deduped -- duplicate detection is quality.py's job, not the normalizer's


def test_normalize_draftables_empty_response():
    games, draftables, skipped, check = normalize_draftables({"draftables": [], "competitions": []}, draft_group_id=1)
    assert check.ok
    assert games == []
    assert draftables == []


DRAFTABLES_SHOWDOWN_PAYLOAD = {
    "draftables": [
        {"draftableId": 1, "displayName": "Cam Schlittler", "position": "SP", "rosterSlotId": 573, "salary": 19500, "teamId": 234, "teamAbbreviation": "NYY", "competition": {"competitionId": 1}},
        {"draftableId": 2, "displayName": "Cam Schlittler", "position": "SP", "rosterSlotId": 574, "salary": 13000, "teamId": 234, "teamAbbreviation": "NYY", "competition": {"competitionId": 1}},
    ],
    "competitions": [],
}


def test_normalize_draftables_showdown_captain_util_variants_both_preserved_as_related_records():
    _, draftables, _, check = normalize_draftables(DRAFTABLES_SHOWDOWN_PAYLOAD, draft_group_id=152391)
    assert check.ok
    assert len(draftables) == 2
    cpt, util = draftables
    assert cpt.roster_slot_id == 573
    assert util.roster_slot_id == 574
    assert cpt.salary == util.salary * 1.5
    assert cpt.display_name == util.display_name  # same underlying player, related variant records, not treated as a collision


DRAFTABLES_NASCAR_PAYLOAD = {
    "draftables": [
        {"draftableId": 1, "displayName": "Ryan Blaney", "position": "D", "rosterSlotId": 92, "salary": 11200, "teamId": -3, "teamAbbreviation": "Nasca", "competition": {"competitionId": 1}},
    ],
    "competitions": [],
}


def test_normalize_draftables_accommodates_non_athlete_entity_shapes():
    # A NASCAR driver has no real team (teamId=-3 sentinel) -- the
    # normalizer must not assume a real team is always present.
    _, draftables, skipped, check = normalize_draftables(DRAFTABLES_NASCAR_PAYLOAD, draft_group_id=1)
    assert check.ok
    assert len(draftables) == 1
    assert draftables[0].team_id == -3
    assert draftables[0].position == "D"
    assert skipped == []


# ----------------------------------------------------------------------------
# Game type rules (Classic + Showdown Captain roster slots/multiplier)
# ----------------------------------------------------------------------------

CLASSIC_RULES_PAYLOAD = {
    "gameTypeId": 2, "gameTypeName": "Classic", "lineupConfigurationId": 2,
    "salaryCap": {"isEnabled": True, "minValue": 0, "maxValue": 50000},
    "gameCount": {"isEnabled": True, "minValue": 2, "maxValue": None},
    "teamCount": {"isEnabled": True, "minValue": 2, "maxValue": None},
    "uniquePlayers": True, "allowLateSwap": True,
    "lineupTemplate": [
        {"rosterSlot": {"id": 110, "name": "P", "description": "Pitcher", "positionTip": None, "positionTipSubtext": None}, "order": 1},
        {"rosterSlot": {"id": 116, "name": "OF", "description": "Outfielder", "positionTip": None, "positionTipSubtext": None}, "order": 8},
    ],
    "rulesUrl": "/help/rules/2/2", "draftType": "SalaryCap", "scoringDivider": None,
}

SHOWDOWN_RULES_PAYLOAD = {
    "gameTypeId": 114, "gameTypeName": "Showdown Captain Mode", "lineupConfigurationId": 114,
    "salaryCap": {"isEnabled": True, "minValue": 0, "maxValue": 50000},
    "gameCount": {"isEnabled": True, "minValue": 1, "maxValue": 1},
    "teamCount": {"isEnabled": True, "minValue": 2, "maxValue": 2},
    "uniquePlayers": True, "allowLateSwap": True,
    "lineupTemplate": [
        {"rosterSlot": {"id": 573, "name": "CPT", "description": "Captain", "positionTip": "Scores 1.5x Fantasy Points", "positionTipSubtext": "1.5x"}, "order": 1},
        {"rosterSlot": {"id": 574, "name": "UTIL", "description": "Utility", "positionTip": None, "positionTipSubtext": None}, "order": 2},
    ],
    "rulesUrl": "/help/rules/2/114", "draftType": "SalaryCap", "scoringDivider": None,
}


def test_normalize_game_type_rules_classic():
    rules, check = normalize_game_type_rules(CLASSIC_RULES_PAYLOAD, sport_id=2)
    assert check.ok
    assert rules.game_type_id == 2
    assert rules.sport_id == 2
    assert rules.salary_cap == 50000
    assert rules.salary_cap_enabled is True
    assert [s.name for s in rules.roster_slots] == ["P", "OF"]
    assert rules.roster_slots[0].scoring_multiplier is None
    assert rules.rules_url == "/help/rules/2/2"


def test_normalize_game_type_rules_showdown_captain_multiplier_parsed():
    rules, check = normalize_game_type_rules(SHOWDOWN_RULES_PAYLOAD, sport_id=2)
    assert check.ok
    cpt = next(s for s in rules.roster_slots if s.name == "CPT")
    util = next(s for s in rules.roster_slots if s.name == "UTIL")
    assert cpt.scoring_multiplier == 1.5
    assert util.scoring_multiplier is None


def test_normalize_game_type_rules_sport_id_none_when_not_supplied():
    rules, check = normalize_game_type_rules(CLASSIC_RULES_PAYLOAD)  # no sport_id passed
    assert check.ok
    assert rules.sport_id is None


def test_normalize_game_type_rules_schema_changed_when_required_key_missing():
    rules, check = normalize_game_type_rules({"gameTypeId": 2})  # missing lineupTemplate/salaryCap
    assert not check.ok
    assert rules is None


def test_normalize_game_type_rules_never_exposes_a_scoring_formula():
    # Explicit negative assertion per this milestone's "do not invent
    # fields" and "DraftKings rules = reference data" instructions --
    # confirms the normalizer doesn't fabricate a points-per-stat table
    # that DraftKings itself never returned.
    rules, _ = normalize_game_type_rules(CLASSIC_RULES_PAYLOAD, sport_id=2)
    assert not hasattr(rules, "scoring_rules")
    assert not hasattr(rules, "points_per_stat")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def test_parse_dotnet_date_valid():
    assert _parse_dotnet_date("/Date(1788306000000)/") == "2026-09-01T23:40:00+00:00"


def test_parse_dotnet_date_missing_or_malformed_returns_none():
    assert _parse_dotnet_date(None) is None
    assert _parse_dotnet_date("") is None
    assert _parse_dotnet_date("not a date") is None


def test_parse_multiplier_valid():
    assert _parse_multiplier("1.5x") == 1.5
    assert _parse_multiplier("2x") == 2.0


def test_parse_multiplier_missing_or_unparseable_returns_none():
    assert _parse_multiplier(None) is None
    assert _parse_multiplier("") is None
    assert _parse_multiplier("Scores extra points") is None
