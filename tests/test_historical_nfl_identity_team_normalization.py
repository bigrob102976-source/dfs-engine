"""NFL M6B -- targeted tests for historical_nfl/identity_team_normalization.py."""

from historical_nfl.identity_team_normalization import is_known_dk_team, normalize_nflverse_team_abbr


def test_real_confirmed_exception_la_to_lar():
    assert normalize_nflverse_team_abbr("LA") == "LAR"


def test_unmapped_code_passes_through_unchanged():
    assert normalize_nflverse_team_abbr("PHI") == "PHI"
    assert normalize_nflverse_team_abbr("BUF") == "BUF"


def test_case_and_whitespace_normalized():
    assert normalize_nflverse_team_abbr(" phi ") == "PHI"


def test_none_or_empty_input_never_raises():
    assert normalize_nflverse_team_abbr(None) == ""
    assert normalize_nflverse_team_abbr("") == ""


def test_is_known_dk_team():
    assert is_known_dk_team("PHI") is True
    assert is_known_dk_team("LAR") is True
    assert is_known_dk_team("LA") is False  # LA is nflverse's spelling, not DK's
    assert is_known_dk_team("ZZZ") is False
