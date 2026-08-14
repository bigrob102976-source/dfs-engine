from research.game_environment.ballpark import get_ballpark_profile


def test_known_team_returns_a_full_profile():
    profile = get_ballpark_profile("COL")
    assert profile is not None
    assert profile.team_abbr == "COL"
    assert profile.venue_name == "Coors Field"
    assert profile.hr_factor > 100  # Coors Field is a well-known extreme hitter's park
    assert profile.altitude_ft > 5000
    assert profile.roof == "open"
    assert profile.surface == "grass"


def test_unknown_team_returns_none_never_a_guess():
    assert get_ballpark_profile("ZZZ") is None


def test_every_real_team_abbreviation_resolves():
    for abbr in ["ARI", "AZ", "ATL", "BAL", "BOS", "CHC", "CWS", "CIN", "CLE", "COL", "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY", "ATH", "OAK", "PHI", "PIT", "SD", "SF", "SEA", "STL", "TB", "TEX", "TOR", "WSH"]:
        profile = get_ballpark_profile(abbr)
        assert profile is not None, f"{abbr} should resolve to a ballpark profile"
        assert 0 < profile.hr_factor < 200
        assert profile.roof in ("open", "dome", "retractable")
        assert profile.surface in ("grass", "turf")


def test_pitcher_friendly_park_has_a_below_average_park_factor():
    profile = get_ballpark_profile("SF")  # Oracle Park is a well-known pitcher's park
    assert profile.park_factor < 100


def test_ari_and_az_resolve_to_the_same_park():
    # team_abbr on the returned profile echoes the INPUT abbreviation, so
    # compare venue identity/factors, not full dataclass equality.
    assert get_ballpark_profile("ARI").venue_name == get_ballpark_profile("AZ").venue_name
    assert get_ballpark_profile("ARI").park_factor == get_ballpark_profile("AZ").park_factor


def test_oak_and_ath_resolve_to_the_same_park():
    assert get_ballpark_profile("OAK").venue_name == get_ballpark_profile("ATH").venue_name
    assert get_ballpark_profile("OAK").park_factor == get_ballpark_profile("ATH").park_factor
