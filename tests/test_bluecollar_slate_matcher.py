from bluecollar.slate_matcher import (
    STATUS_AMBIGUOUS,
    STATUS_MATCHED,
    STATUS_NO_BLUECOLLAR_SLATES,
    STATUS_NO_CANDIDATE,
    match_dk_slate_to_bluecollar,
    parse_bluecollar_slate_name,
)
from external_projections.models import ExternalSlateInfo


def bc_slate(slate_id, name, player_count):
    return ExternalSlateInfo(slate_id=slate_id, slate_name=name, sport="MLB", site="draftkings", player_count=player_count)


def dk_slate(slate_id="dk-main", game_count=8, player_count=746, start_time="2026-08-23T17:35:00Z", slate_name="Featured"):
    return {"slate_id": slate_id, "game_count": game_count, "player_count": player_count, "start_time": start_time, "slate_name": slate_name}


# ---------------------------------------------------------------------------
# parse_bluecollar_slate_name -- the observed live naming convention.
# ---------------------------------------------------------------------------


def test_parses_the_real_observed_main_slate_name():
    parsed = parse_bluecollar_slate_name("1:35PM ET Main 8 Games")
    assert parsed.start_hour_et == 13
    assert parsed.start_minute_et == 35
    assert parsed.type_word == "main"
    assert parsed.game_count == 8


def test_parses_a_parenthesized_turbo_name():
    parsed = parse_bluecollar_slate_name("2:10PM ET (Turbo) 4 Games")
    assert parsed.start_hour_et == 14
    assert parsed.start_minute_et == 10
    assert parsed.type_word == "turbo"
    assert parsed.game_count == 4


def test_parses_an_am_time_correctly_including_12am_midnight():
    parsed = parse_bluecollar_slate_name("12:00AM ET Main 1 Games")
    assert parsed.start_hour_et == 0


def test_parses_12pm_as_noon():
    parsed = parse_bluecollar_slate_name("12:00PM ET Main 1 Games")
    assert parsed.start_hour_et == 12


def test_returns_none_for_an_unparseable_name_never_raises():
    assert parse_bluecollar_slate_name("Something BlueCollar Might Change To Someday") is None
    assert parse_bluecollar_slate_name(None) is None
    assert parse_bluecollar_slate_name("") is None


# ---------------------------------------------------------------------------
# match_dk_slate_to_bluecollar -- the real live scenario (4 slates).
# ---------------------------------------------------------------------------


def _real_bluecollar_slates():
    return [
        bc_slate("bc-main", "1:35PM ET Main 8 Games", 746),
        bc_slate("bc-turbo-1", "2:10PM ET (Turbo) 4 Games", 382),
        bc_slate("bc-turbo-2", "3:10PM ET (Turbo) 2 Games", 182),
        bc_slate("bc-afternoon", "4:10PM ET (Afternoon) 4 Games", 377),
    ]


def test_matches_the_dk_main_slate_to_the_only_8_game_bluecollar_slate():
    dk = dk_slate(game_count=8, player_count=746, start_time="2026-08-23T17:35:00Z", slate_name="Featured")
    result = match_dk_slate_to_bluecollar(dk, _real_bluecollar_slates())
    assert result.status == STATUS_MATCHED
    assert result.bluecollar_slate_id == "bc-main"


def test_matches_a_dk_turbo_slate_by_game_count_when_game_counts_differ():
    # 2 real Turbo slates exist (4 games and 2 games) -- game_count alone
    # already disambiguates them, exactly like the live 2026-08-23 data.
    dk = dk_slate(slate_id="dk-turbo-2game", game_count=2, player_count=182, start_time="2026-08-23T19:10:00Z", slate_name="Turbo")
    result = match_dk_slate_to_bluecollar(dk, _real_bluecollar_slates())
    assert result.status == STATUS_MATCHED
    assert result.bluecollar_slate_id == "bc-turbo-2"


def test_matches_the_afternoon_slate_correctly():
    dk = dk_slate(slate_id="dk-afternoon", game_count=4, player_count=377, start_time="2026-08-23T20:10:00Z", slate_name="Afternoon")
    result = match_dk_slate_to_bluecollar(dk, _real_bluecollar_slates())
    assert result.status == STATUS_MATCHED
    assert result.bluecollar_slate_id == "bc-afternoon"


def test_disambiguates_two_turbo_slates_with_the_same_game_count_by_start_time():
    bluecollar_slates = [
        bc_slate("bc-turbo-early", "2:10PM ET (Turbo) 4 Games", 380),
        bc_slate("bc-turbo-late", "6:10PM ET (Turbo) 4 Games", 380),
    ]
    dk = dk_slate(game_count=4, player_count=380, start_time="2026-08-23T18:10:00Z", slate_name="Turbo")  # 2:10PM ET
    result = match_dk_slate_to_bluecollar(dk, bluecollar_slates)
    assert result.status == STATUS_MATCHED
    assert result.bluecollar_slate_id == "bc-turbo-early"


def test_rejects_ambiguous_match_when_no_signal_can_separate_two_candidates():
    # Same game count, no start_time on the DK side, no name overlap, and
    # nearly identical player counts -- nothing to disambiguate on.
    bluecollar_slates = [
        bc_slate("bc-x", "2:10PM ET (Turbo) 4 Games", 380),
        bc_slate("bc-y", "2:11PM ET (Snake) 4 Games", 381),
    ]
    dk = dk_slate(game_count=4, player_count=380, start_time=None, slate_name=None)
    result = match_dk_slate_to_bluecollar(dk, bluecollar_slates)
    assert result.status == STATUS_AMBIGUOUS
    assert set(result.candidate_slate_ids) == {"bc-x", "bc-y"}
    assert "BLUECOLLAR_SLATE_MATCH" not in result.status.upper()  # status itself is the plain word; the CLI prefixes it


def test_never_guesses_the_first_slate_when_ambiguous():
    bluecollar_slates = [
        bc_slate("bc-first", "2:10PM ET (Turbo) 4 Games", 380),
        bc_slate("bc-second", "2:10PM ET (Snake) 4 Games", 380),
    ]
    dk = dk_slate(game_count=4, player_count=380, start_time=None, slate_name=None)
    result = match_dk_slate_to_bluecollar(dk, bluecollar_slates)
    assert result.status == STATUS_AMBIGUOUS
    assert result.bluecollar_slate_id is None


def test_no_bluecollar_slates_at_all():
    dk = dk_slate()
    result = match_dk_slate_to_bluecollar(dk, [])
    assert result.status == STATUS_NO_BLUECOLLAR_SLATES
    assert result.bluecollar_slate_id is None


def test_no_candidate_when_game_count_matches_nothing():
    dk = dk_slate(game_count=99)
    result = match_dk_slate_to_bluecollar(dk, _real_bluecollar_slates())
    assert result.status == STATUS_NO_CANDIDATE


def test_excludes_unparseable_bluecollar_slate_names_from_matching():
    bluecollar_slates = [
        bc_slate("bc-weird", "A Totally New Format BlueCollar Might Use", 746),
        bc_slate("bc-main", "1:35PM ET Main 8 Games", 746),
    ]
    dk = dk_slate(game_count=8)
    result = match_dk_slate_to_bluecollar(dk, bluecollar_slates)
    assert result.status == STATUS_MATCHED
    assert result.bluecollar_slate_id == "bc-main"  # never the unparseable one, even with equal player_count
