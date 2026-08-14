from external_projections.csv_import.column_detection import detect_columns


def test_detects_common_synonyms():
    detected = detect_columns(["Player Name", "Team", "Salary", "Proj", "Own%", "Pos", "Opp", "Ceiling", "Floor"])
    assert detected["name"] == "Player Name"
    assert detected["team"] == "Team"
    assert detected["salary"] == "Salary"
    assert detected["projection"] == "Proj"
    assert detected["ownership"] == "Own%"
    assert detected["position"] == "Pos"
    assert detected["opponent"] == "Opp"
    assert detected["ceiling"] == "Ceiling"
    assert detected["floor"] == "Floor"


def test_leaves_undetected_fields_none():
    detected = detect_columns(["Player", "Team"])
    assert detected["slate"] is None
    assert detected["player_id"] is None
    assert detected["ownership"] is None


def test_case_and_punctuation_insensitive():
    detected = detect_columns(["  PLAYER NAME  ", "own_pct", "FPTS"])
    assert detected["name"] == "  PLAYER NAME  "
    assert detected["ownership"] == "own_pct"
    assert detected["projection"] == "FPTS"


def test_first_matching_header_wins_for_a_field():
    detected = detect_columns(["Name", "Player Name"])
    assert detected["name"] == "Name"


def test_empty_headers_list_detects_nothing():
    detected = detect_columns([])
    assert all(v is None for v in detected.values())
