from research.game_environment.travel import build_travel_profile


def test_home_team_travels_zero_distance():
    profile = build_travel_profile("PHI", "COL", is_home=True)
    assert profile.status == "KNOWN"
    assert profile.distance_miles == 0.0
    assert profile.timezones_crossed == 0


def test_away_team_travels_a_positive_distance():
    profile = build_travel_profile("COL", "PHI", is_home=False)
    assert profile.status == "KNOWN"
    assert profile.distance_miles is not None
    assert profile.distance_miles > 0


def test_coast_to_coast_travel_crosses_multiple_timezones():
    # Away team based in NY (Eastern), traveling to a game in LA (Pacific).
    profile = build_travel_profile("NYY", "LAD", is_home=False)
    assert profile.timezones_crossed == 3


def test_same_timezone_travel_crosses_zero_timezones():
    # Both teams' home cities are in the Eastern timezone.
    profile = build_travel_profile("NYY", "BOS", is_home=False)
    assert profile.timezones_crossed == 0


def test_back_to_back_and_getaway_day_are_always_unknown():
    """No game-by-game schedule history is collected yet -- these two
    fields must never be guessed, per the milestone's explicit
    "Only if data available. Otherwise UNKNOWN" instruction."""
    profile = build_travel_profile("COL", "PHI", is_home=False)
    assert profile.back_to_back is None
    assert profile.getaway_day is None


def test_unknown_team_abbreviation_reports_unknown_status_never_a_guess():
    profile = build_travel_profile("ZZZ", "PHI", is_home=False)
    assert profile.status == "UNKNOWN"
    assert profile.distance_miles is None
    assert profile.timezones_crossed is None


def test_distance_is_symmetric_regardless_of_who_is_designated_home():
    a = build_travel_profile("COL", "PHI", is_home=False)
    b = build_travel_profile("PHI", "COL", is_home=True)
    # a: COL traveling to PHI's park. b: PHI at home (0 distance) -- not
    # symmetric by definition, so instead verify against the reverse pairing.
    c = build_travel_profile("PHI", "COL", is_home=False)  # PHI traveling to COL's park
    assert a.distance_miles == c.distance_miles
