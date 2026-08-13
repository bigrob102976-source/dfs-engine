from dfs.team_abbreviations import normalize_dk_team_abbr


def test_arizona_maps_to_az():
    assert normalize_dk_team_abbr("ARI") == "AZ"


def test_athletics_oak_maps_to_ath():
    assert normalize_dk_team_abbr("OAK") == "ATH"


def test_unmapped_team_passes_through():
    assert normalize_dk_team_abbr("NYY") == "NYY"
    assert normalize_dk_team_abbr("BOS") == "BOS"


def test_case_insensitive_and_trimmed():
    assert normalize_dk_team_abbr(" ari ") == "AZ"


def test_empty_string_passes_through():
    assert normalize_dk_team_abbr("") == ""
