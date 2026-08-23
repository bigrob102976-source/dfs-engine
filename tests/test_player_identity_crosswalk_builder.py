from player_identity.crosswalk_builder import build_team_identities


def _entry(mlb_id="1", name="Test Player", position="OF", player_type="hitter", active=True):
    return {"mlb_player_id": mlb_id, "name": name, "position_abbr": position, "player_type": player_type, "active": active}


def test_build_team_identities_sets_current_team_from_the_team_this_roster_was_fetched_for():
    identities = build_team_identities("NYY", [_entry()], "2026-08-23T18:00:00+00:00")
    assert identities[0].current_team == "NYY"


def test_build_team_identities_normalizes_the_name():
    identities = build_team_identities("PHI", [_entry(name="Carlos Rodón")], "2026-08-23T18:00:00+00:00")
    assert identities[0].normalized_name == "carlos rodon"
    assert identities[0].canonical_name == "Carlos Rodón"  # display name unchanged


def test_build_team_identities_carries_player_type_and_position_through():
    identities = build_team_identities("NYY", [_entry(position="P", player_type="pitcher")], "2026-08-23T18:00:00+00:00")
    assert identities[0].player_type == "pitcher"
    assert identities[0].position == "P"


def test_build_team_identities_leaves_handedness_none_when_no_backfill_given():
    identities = build_team_identities("NYY", [_entry()], "2026-08-23T18:00:00+00:00")
    assert identities[0].bat_side is None
    assert identities[0].throw_hand is None


def test_build_team_identities_applies_handedness_backfill_by_mlb_id():
    identities = build_team_identities(
        "NYY", [_entry(mlb_id="607074")], "2026-08-23T18:00:00+00:00",
        handedness_by_mlb_id={"607074": ("S", "L")},
    )
    assert identities[0].bat_side == "S"
    assert identities[0].throw_hand == "L"


def test_build_team_identities_backfill_is_id_scoped_never_leaks_to_other_players():
    identities = build_team_identities(
        "NYY", [_entry(mlb_id="1"), _entry(mlb_id="2")], "2026-08-23T18:00:00+00:00",
        handedness_by_mlb_id={"1": ("L", "R")},
    )
    by_id = {i.mlb_player_id: i for i in identities}
    assert by_id["1"].bat_side == "L"
    assert by_id["2"].bat_side is None


def test_build_team_identities_sets_last_verified_at_and_source():
    identities = build_team_identities("NYY", [_entry()], "2026-08-23T18:00:00+00:00")
    assert identities[0].last_verified_at == "2026-08-23T18:00:00+00:00"
    assert identities[0].source == "mlb_roster"


def test_build_team_identities_carries_active_status():
    identities = build_team_identities("NYY", [_entry(active=False)], "2026-08-23T18:00:00+00:00")
    assert identities[0].active is False


def test_build_team_identities_empty_roster_yields_empty_list():
    assert build_team_identities("NYY", [], "2026-08-23T18:00:00+00:00") == []
