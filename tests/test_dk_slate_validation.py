from dfs.models import DKSalaryRow
from dfs.slate_validation import parse_game_info, validate_slate


def _dk_row(game_info, team="NYY"):
    return DKSalaryRow(dk_player_id="1", name="X Y", team_abbrev=team, dk_positions=["OF"],
                        salary=4000, game_info=game_info)


def _game(game_id, away, home, dt_utc):
    return {"game_id": game_id, "away_team_abbr": away, "home_team_abbr": home, "game_datetime_utc": dt_utc}


def test_parse_game_info_standard_format():
    parsed = parse_game_info("NYY@BOS 07:05PM ET")
    assert parsed.away_abbrev == "NYY"
    assert parsed.home_abbrev == "BOS"
    assert parsed.time_text == "07:05PM"


def test_parse_game_info_unparseable_falls_back_gracefully():
    parsed = parse_game_info("garbage string")
    assert parsed.away_abbrev is None
    assert parsed.home_abbrev is None


def test_single_game_matches_directly():
    games = [_game("111", "NYY", "BOS", "2026-08-11T23:05:00+00:00")]
    dk_rows = [_dk_row("NYY@BOS 07:05PM ET")]
    result = validate_slate(dk_rows, {"games": games})
    match = result.dk_game_matches["NYY@BOS 07:05PM ET"]
    assert match.status == "matched"
    assert match.research_game_id == "111"
    assert result.research_games_not_on_dk_slate == []


def test_team_abbreviation_difference_still_resolves():
    # research uses AZ; DraftKings uses ARI.
    games = [_game("222", "ARI", "SD", "2026-08-11T23:05:00+00:00")]
    games[0]["away_team_abbr"] = "AZ"  # what the research package actually stores
    dk_rows = [_dk_row("ARI@SD 07:05PM ET")]
    result = validate_slate(dk_rows, {"games": games})
    assert result.dk_game_matches["ARI@SD 07:05PM ET"].status == "matched"


def test_dk_game_not_in_research_reported_unmatched():
    games = [_game("111", "NYY", "BOS", "2026-08-11T23:05:00+00:00")]
    dk_rows = [_dk_row("LAA@SEA 10:10PM ET")]
    result = validate_slate(dk_rows, {"games": games})
    assert result.dk_game_matches["LAA@SEA 10:10PM ET"].status == "unmatched"


def test_research_game_with_no_dk_counterpart_reported():
    games = [_game("111", "NYY", "BOS", "2026-08-11T23:05:00+00:00"),
             _game("222", "LAA", "SEA", "2026-08-12T02:10:00+00:00")]
    dk_rows = [_dk_row("NYY@BOS 07:05PM ET")]  # DK slate excludes the LAA@SEA game
    result = validate_slate(dk_rows, {"games": games})
    excluded_ids = {g["game_id"] for g in result.research_games_not_on_dk_slate}
    assert excluded_ids == {"222"}


def test_doubleheader_disambiguated_by_time():
    # Two research games between the same teams (a doubleheader), 3 hours apart.
    games = [
        _game("g1", "NYY", "BOS", "2026-08-11T17:05:00+00:00"),  # 1:05 PM ET
        _game("g2", "NYY", "BOS", "2026-08-11T23:35:00+00:00"),  # 7:35 PM ET
    ]
    dk_rows = [_dk_row("NYY@BOS 07:35PM ET")]
    result = validate_slate(dk_rows, {"games": games})
    assert result.dk_game_matches["NYY@BOS 07:35PM ET"].research_game_id == "g2"


def test_doubleheader_unresolvable_time_is_ambiguous_not_guessed():
    games = [
        _game("g1", "NYY", "BOS", "2026-08-11T17:05:00+00:00"),
        _game("g2", "NYY", "BOS", "2026-08-11T23:35:00+00:00"),
    ]
    dk_rows = [_dk_row("NYY@BOS 09:00PM ET")]  # matches neither game's time
    result = validate_slate(dk_rows, {"games": games})
    match = result.dk_game_matches["NYY@BOS 09:00PM ET"]
    assert match.status == "ambiguous_doubleheader"
    assert match.research_game_id is None


def test_unparseable_game_info_does_not_crash():
    games = [_game("111", "NYY", "BOS", "2026-08-11T23:05:00+00:00")]
    dk_rows = [_dk_row("Postponed")]
    result = validate_slate(dk_rows, {"games": games})
    assert result.dk_game_matches["Postponed"].status == "unparseable"
