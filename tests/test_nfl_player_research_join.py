"""NFL M5 -- targeted tests for nfl/player_research_join.py."""

from nfl.game_context_models import NflGameContext
from nfl.models import NflPlayer
from nfl.player_research_join import attach_game_context

DG_ID = 151307
DATE = "2026-09-13"


def _player(pid, name, position, game_id, is_team_entity=False):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id=f"dk{pid}", draftable_ids=[f"d{pid}"], name=name,
        first_name=name, last_name=None, is_team_entity=is_team_entity, position=position,
        roster_slots=[position], team="PHI", opponent="DAL", game_id=game_id, game_description="DAL @ PHI",
        game_start_time="2026-09-13T17:00:00Z", salary=6000, status="None", injury_status=None,
        draft_group_id=DG_ID, slate_date=DATE, slate_name="Featured", source="draftkings_unofficial",
        source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def _game(game_id):
    return NflGameContext(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, canonical_game_id=game_id, draftkings_game_id=game_id,
        home_team="PHI", away_team="DAL", spread=-3.0, total=47.5,
    )


def test_player_with_matching_game_gets_context():
    players = [_player("1", "QB One", "QB", "100")]
    games = [_game("100")]
    result = attach_game_context(players, games)
    assert len(result) == 1
    assert result[0].game is not None
    assert result[0].game.canonical_game_id == "100"


def test_player_with_no_game_context_yet_gets_none():
    """No odds provider is configured today -- this is the expected,
    honest current state for every player until real odds are matched."""
    players = [_player("1", "QB One", "QB", "999")]
    games = [_game("100")]
    result = attach_game_context(players, games)
    assert result[0].game is None


def test_dst_resolves_correctly_like_any_other_player():
    players = [_player("4", "Team DST", "DST", "100", is_team_entity=True)]
    games = [_game("100")]
    result = attach_game_context(players, games)
    assert result[0].game is not None
    assert result[0].player.is_team_entity is True


def test_original_player_fields_never_overwritten():
    players = [_player("1", "QB One", "QB", "100")]
    games = [_game("100")]
    result = attach_game_context(players, games)
    assert result[0].player.salary == 6000  # untouched DK salary field
    assert result[0].player.team == "PHI"   # untouched DK identity field


def test_no_games_at_all_leaves_every_player_unmatched():
    players = [_player("1", "QB One", "QB", "100"), _player("4", "Team DST", "DST", "100", is_team_entity=True)]
    result = attach_game_context(players, [])
    assert all(r.game is None for r in result)
