from external_projections.models import ExternalProjectionPlayer
from external_projections.validator import validate_external_players


def _player(**overrides) -> ExternalProjectionPlayer:
    base = dict(
        external_player_id="ext-1", name="Test Player", team="BOS", position="OF", projection=10.0,
        provider_name="MOCK EXTERNAL PROJECTIONS", updated_at="2026-08-11T18:00:00Z", slate_id="s1",
    )
    base.update(overrides)
    return ExternalProjectionPlayer(**base)


def test_no_warnings_for_a_clean_player():
    assert validate_external_players([_player()]) == []


def test_empty_list_warns():
    warnings = validate_external_players([])
    assert len(warnings) == 1
    assert "zero players" in warnings[0].lower()


def test_missing_external_player_id_warns():
    warnings = validate_external_players([_player(external_player_id="")])
    assert any("external_player_id" in w for w in warnings)


def test_duplicate_external_player_id_warns():
    warnings = validate_external_players([_player(external_player_id="dup"), _player(external_player_id="dup", name="Other")])
    assert any("Duplicate external_player_id" in w for w in warnings)


def test_negative_projection_warns():
    warnings = validate_external_players([_player(projection=-1.0)])
    assert any("negative projection" in w for w in warnings)


def test_non_numeric_projection_warns():
    warnings = validate_external_players([_player(projection="not-a-number")])
    assert any("non-numeric projection" in w for w in warnings)


def test_ceiling_below_floor_warns():
    warnings = validate_external_players([_player(ceiling=5.0, floor=10.0)])
    assert any("ceiling" in w.lower() and "floor" in w.lower() for w in warnings)


def test_out_of_range_ownership_warns():
    warnings = validate_external_players([_player(ownership_projection=150.0)])
    assert any("ownership_projection" in w for w in warnings)


def test_missing_provenance_fields_warn():
    warnings = validate_external_players([_player(provider_name="", updated_at="", slate_id="")])
    assert any("provider_name" in w for w in warnings)
    assert any("updated_at" in w for w in warnings)
    assert any("slate_id" in w for w in warnings)
