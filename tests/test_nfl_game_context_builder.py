"""NFL M7 -- targeted tests for nfl/game_context_builder.py's
orchestration. No network calls: fetch_nfl_odds_events is monkeypatched."""

import nfl.game_context_builder as builder_module
from nfl.models import NflPlayer
from nfl.odds_provider import NflOddsFetchResult, NOT_CONFIGURED, SPORTSGAMEODDS_CONFIGURED
from research.game_environment.providers.models import BookLine, NormalizedGameOdds

DG_ID = 151307
DATE = "2026-09-13"


def _player(pid, game_id, game_description):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id=f"dk{pid}", draftable_ids=[f"d{pid}"], name=f"Player {pid}",
        first_name=None, last_name=None, is_team_entity=False, position="QB", roster_slots=["QB"],
        team="KC", opponent="BUF", game_id=game_id, game_description=game_description, game_start_time="2026-09-13T17:00:00Z",
        salary=6000, status="None", injury_status=None, draft_group_id=DG_ID, slate_date=DATE, slate_name="Featured",
        source="draftkings_unofficial", source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def test_build_with_no_configured_provider_leaves_every_game_unmatched(monkeypatch):
    monkeypatch.setattr(
        builder_module, "fetch_nfl_odds_events",
        lambda: NflOddsFetchResult(events=[], source_provenance=NOT_CONFIGURED, provider_errors=[]),
    )
    players = [_player("1", "100", "BUF @ KC")]
    result = builder_module.build_nfl_game_context(players, DG_ID, DATE)
    assert result.dk_game_count == 1
    assert result.match_result.unmatched_dk_game_ids == ["100"]
    assert result.match_result.games == []
    assert result.odds_fetch.source_provenance == NOT_CONFIGURED


def test_build_with_real_matching_event_attaches_context(monkeypatch):
    event = NormalizedGameOdds(
        provider="sportsgameodds", event_id="evt1", league="NFL", home_team="KC", away_team="BUF",
        game_time_utc="2026-09-13T17:00:00Z", retrieved_at="2026-09-13T12:00:00Z",
        books=[BookLine(book="draftkings", home_moneyline=-150, away_moneyline=130, total=48.5, home_run_line=-2.5)],
    )
    monkeypatch.setattr(
        builder_module, "fetch_nfl_odds_events",
        lambda: NflOddsFetchResult(events=[event], source_provenance=SPORTSGAMEODDS_CONFIGURED, provider_errors=[]),
    )
    players = [_player("1", "100", "BUF @ KC")]
    result = builder_module.build_nfl_game_context(players, DG_ID, DATE)
    assert result.match_result.matched_dk_game_ids == ["100"]
    game = result.match_result.games[0]
    assert game.spread == -2.5
    assert game.total == 48.5
    assert game.home_implied_total is not None
