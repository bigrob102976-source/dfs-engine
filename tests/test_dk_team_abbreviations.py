from dfs.team_abbreviations import MLB_FULL_NAME_TO_ABBR, normalize_dk_team_abbr, normalize_full_team_name


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


# ----------------------------------------------------------------------------
# Milestone 27 -- full-name crosswalk (The Odds API returns full names)
# ----------------------------------------------------------------------------


def test_all_30_teams_present_and_unique():
    assert len(MLB_FULL_NAME_TO_ABBR) >= 30
    # Every VALUE (abbreviation) must be one this project's own BALLPARKS
    # config recognizes -- imported lazily to avoid a module-load cycle.
    from config.game_environment_config import BALLPARKS

    for abbr in set(MLB_FULL_NAME_TO_ABBR.values()):
        assert abbr in BALLPARKS, f"{abbr} not a recognized research-package abbreviation"


def test_normalize_full_team_name_dodgers_and_rockies():
    assert normalize_full_team_name("Los Angeles Dodgers") == "LAD"
    assert normalize_full_team_name("Colorado Rockies") == "COL"


def test_normalize_full_team_name_unrecognized_returns_none():
    assert normalize_full_team_name("Brooklyn Dodgers") is None


def test_normalize_full_team_name_empty_returns_none():
    assert normalize_full_team_name("") is None
