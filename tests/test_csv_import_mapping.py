from external_projections.csv_import.mapping import apply_mapping, resolve_mapping


def test_resolve_mapping_manual_override_wins():
    detected = {"name": "Player", "projection": "Proj", "salary": None}
    resolved = resolve_mapping(detected, {"projection": "FPTS Alt"})
    assert resolved["projection"] == "FPTS Alt"
    assert resolved["name"] == "Player"


def test_resolve_mapping_manual_unmap_with_empty_string():
    detected = {"name": "Player", "salary": "Salary"}
    resolved = resolve_mapping(detected, {"salary": ""})
    assert resolved["salary"] is None


def test_resolve_mapping_ignores_unknown_field_keys():
    resolved = resolve_mapping({"name": "Player"}, {"not_a_real_field": "X"})
    assert "not_a_real_field" not in resolved


def test_apply_mapping_coerces_numeric_fields():
    mapping = {"name": "Player", "salary": "Salary", "projection": "Proj", "ownership": "Own%"}
    rows = [{"Player": "Aaron Judge", "Salary": "$6,500", "Proj": "12.5", "Own%": "24.3%"}]
    normalized = apply_mapping(rows, mapping)
    assert normalized[0]["name"] == "Aaron Judge"
    assert normalized[0]["salary"] == 6500
    assert normalized[0]["projection"] == 12.5
    assert normalized[0]["ownership"] == 24.3


def test_apply_mapping_leaves_unmapped_fields_none():
    mapping = {"name": "Player"}
    rows = [{"Player": "Aaron Judge"}]
    normalized = apply_mapping(rows, mapping)
    assert normalized[0]["team"] is None
    assert normalized[0]["salary"] is None
    assert normalized[0]["ceiling"] is None


def test_apply_mapping_unparseable_numeric_becomes_none_not_zero():
    mapping = {"name": "Player", "projection": "Proj"}
    rows = [{"Player": "Aaron Judge", "Proj": "N/A"}]
    normalized = apply_mapping(rows, mapping)
    assert normalized[0]["projection"] is None


def test_apply_mapping_blank_string_field_becomes_none():
    mapping = {"name": "Player", "team": "Team"}
    rows = [{"Player": "Aaron Judge", "Team": "   "}]
    normalized = apply_mapping(rows, mapping)
    assert normalized[0]["team"] is None
