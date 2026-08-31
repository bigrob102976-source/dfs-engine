"""NFL M5 -- targeted tests for nfl/odds_matching.py. All fixtures are
synthetic; no network calls (no real odds provider is configured
anywhere in this project today -- see that module's own docstring)."""

from nfl.game_context_models import NflGameContext
from nfl.models import NflPlayer
from nfl.odds_matching import DkGameInfo, derive_dk_games_from_pool, match_dk_games_to_odds
from research.game_environment.providers.models import BookLine, NormalizedGameOdds

DG_ID = 151307
DATE = "2026-09-13"


def _player(pid, game_id, game_description, team="PHI", start_time="2026-09-13T17:00:00Z"):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id=f"dk{pid}", draftable_ids=[f"d{pid}"], name=f"Player {pid}",
        first_name=None, last_name=None, is_team_entity=False, position="QB", roster_slots=["QB"],
        team=team, opponent="DAL", game_id=game_id, game_description=game_description, game_start_time=start_time,
        salary=6000, status="None", injury_status=None, draft_group_id=DG_ID, slate_date=DATE, slate_name="Featured",
        source="draftkings_unofficial", source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def _odds_event(event_id, home, away, spread=-3.0, total=47.5):
    return NormalizedGameOdds(
        provider="sportsgameodds", event_id=event_id, league="NFL", home_team=home, away_team=away,
        game_time_utc="2026-09-13T17:00:00Z", retrieved_at="2026-09-13T12:00:00Z",
        books=[BookLine(book="draftkings", home_moneyline=-160, away_moneyline=140, total=total, home_run_line=spread, last_updated="2026-09-13T11:00:00Z")],
    )


def test_derive_dk_games_from_pool_extracts_unique_games():
    players = [
        _player("1", "100", "DAL @ PHI"),
        _player("2", "100", "DAL @ PHI"),  # same game, second player -- must dedupe
        _player("3", "200", "SEA @ SF"),
    ]
    games = derive_dk_games_from_pool(players)
    assert len(games) == 2
    by_id = {g.game_id: g for g in games}
    assert by_id["100"].home_team == "PHI"
    assert by_id["100"].away_team == "DAL"
    assert by_id["200"].home_team == "SF"
    assert by_id["200"].away_team == "SEA"


def test_derive_dk_games_skips_players_with_no_parseable_game_description():
    players = [_player("1", "100", None)]
    games = derive_dk_games_from_pool(players)
    assert games == []


def test_matched_game_gets_real_odds_attached():
    dk_games = [DkGameInfo(game_id="100", home_team="PHI", away_team="DAL", start_time="2026-09-13T17:00:00Z")]
    odds = [_odds_event("evt1", "PHI", "DAL")]
    result = match_dk_games_to_odds(dk_games, odds, DG_ID, DATE, source="sportsgameodds")
    assert result.matched_dk_game_ids == ["100"]
    assert len(result.games) == 1
    game = result.games[0]
    assert game.spread == -3.0
    assert game.total == 47.5
    assert game.external_event_id == "evt1"
    assert game.source_provenance == "sportsgameodds"
    assert game.home_implied_total is not None  # derived since both spread and total are real


def test_unmatched_dk_game_when_no_odds_event_for_that_pair():
    dk_games = [DkGameInfo(game_id="100", home_team="PHI", away_team="DAL", start_time=None)]
    odds = [_odds_event("evt1", "SEA", "SF")]
    result = match_dk_games_to_odds(dk_games, odds, DG_ID, DATE, source="sportsgameodds")
    assert result.unmatched_dk_game_ids == ["100"]
    assert result.games == []


def test_no_odds_events_at_all_leaves_every_game_unmatched():
    """The current, honest, real state of this project -- no odds
    provider is configured anywhere."""
    dk_games = [DkGameInfo(game_id="100", home_team="PHI", away_team="DAL", start_time=None)]
    result = match_dk_games_to_odds(dk_games, [], DG_ID, DATE, source="sportsgameodds")
    assert result.unmatched_dk_game_ids == ["100"]
    assert result.matched_dk_game_ids == []
    assert result.games == []


def test_ambiguous_when_two_odds_events_share_the_same_normalized_pair():
    dk_games = [DkGameInfo(game_id="100", home_team="PHI", away_team="DAL", start_time=None)]
    odds = [_odds_event("evt1", "PHI", "DAL"), _odds_event("evt2", "PHI", "DAL")]
    result = match_dk_games_to_odds(dk_games, odds, DG_ID, DATE, source="sportsgameodds")
    assert result.ambiguous_dk_game_ids == ["100"]
    assert result.games == []  # never attaches either candidate when ambiguous


def test_team_abbreviation_exception_is_applied(monkeypatch):
    """Proves the normalization mechanism works when a real exception is
    registered -- config/nfl_team_abbreviations.py's real table is
    deliberately empty today (no verified provider payload exists yet),
    so this test injects one to verify the MECHANISM, not real data."""
    import config.nfl_team_abbreviations as team_abbr_module
    monkeypatch.setitem(team_abbr_module.ODDS_PROVIDER_TO_DK_TEAM_ABBR, "WSH", "WAS")

    dk_games = [DkGameInfo(game_id="100", home_team="WAS", away_team="DAL", start_time=None)]
    odds = [_odds_event("evt1", "WSH", "DAL")]  # provider uses "WSH", DK uses "WAS"
    result = match_dk_games_to_odds(dk_games, odds, DG_ID, DATE, source="sportsgameodds")
    assert result.matched_dk_game_ids == ["100"]


def test_missing_book_data_leaves_odds_fields_none_not_fabricated():
    dk_games = [DkGameInfo(game_id="100", home_team="PHI", away_team="DAL", start_time=None)]
    event = NormalizedGameOdds(provider="sportsgameodds", event_id="evt1", league="NFL", home_team="PHI", away_team="DAL", game_time_utc=None, retrieved_at="2026-09-13T12:00:00Z", books=[])
    result = match_dk_games_to_odds(dk_games, [event], DG_ID, DATE, source="sportsgameodds")
    assert result.matched_dk_game_ids == ["100"]
    game = result.games[0]
    assert game.spread is None
    assert game.total is None
    assert game.home_implied_total is None
    assert game.implied_total_derivation is None
