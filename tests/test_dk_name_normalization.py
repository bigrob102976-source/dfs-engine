from dfs.name_normalization import normalize_name


def test_accent_stripping():
    assert normalize_name("Ronald Acuña Jr.") == "ronald acuna"


def test_suffix_stripping_jr():
    assert normalize_name("Luis Garcia Jr.") == "luis garcia"


def test_suffix_stripping_various():
    assert normalize_name("Mike Foo III") == "mike foo"
    assert normalize_name("Mike Foo II") == "mike foo"
    assert normalize_name("Mike Foo Sr.") == "mike foo"


def test_hyphen_becomes_space():
    assert normalize_name("Pete Crow-Armstrong") == "pete crow armstrong"


def test_periods_removed_no_space_inserted():
    assert normalize_name("T.J. Friedl") == "tj friedl"


def test_apostrophe_removed():
    assert normalize_name("O'Brien") == "obrien"


def test_extra_whitespace_collapsed():
    assert normalize_name("  Aaron   Judge  ") == "aaron judge"


def test_case_insensitive():
    assert normalize_name("AARON JUDGE") == normalize_name("aaron judge")


def test_empty_string():
    assert normalize_name("") == ""


def test_both_sides_of_a_real_match_normalize_identically():
    # A DK export name and our research name for the same player, with
    # slightly different formatting -- must collapse to the same string.
    assert normalize_name("Luis García Jr.") == normalize_name("Luis Garcia Jr")


def test_different_players_do_not_accidentally_collapse():
    assert normalize_name("Will Smith") != normalize_name("Will Smyth")
