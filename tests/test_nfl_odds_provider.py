"""NFL M7 -- targeted tests for nfl/odds_provider.py's resolution and
fetch orchestration. No real network calls: provider HTTP methods are
monkeypatched."""

import nfl.odds_provider as odds_provider_module
from nfl.odds_provider import (
    MULTI_PROVIDER_CONFIGURED,
    NOT_CONFIGURED,
    SPORTSGAMEODDS_CONFIGURED,
    THEODDSAPI_ONLY_CONFIGURED,
    fetch_nfl_odds_events,
    get_nfl_odds_source_provenance,
)
from research.game_environment.providers.base import OddsProviderAuthenticationError
from research.game_environment.providers.models import BookLine, NormalizedGameOdds


def test_no_keys_set_is_not_configured(monkeypatch):
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    assert get_nfl_odds_source_provenance() == NOT_CONFIGURED


def test_sportsgameodds_key_only(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "fake_key")
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    assert get_nfl_odds_source_provenance() == SPORTSGAMEODDS_CONFIGURED


def test_theoddsapi_key_only(monkeypatch):
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake_key")
    assert get_nfl_odds_source_provenance() == THEODDSAPI_ONLY_CONFIGURED


def test_both_keys_set_is_multi_provider(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "fake_key")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake_key_2")
    assert get_nfl_odds_source_provenance() == MULTI_PROVIDER_CONFIGURED


def test_fetch_returns_empty_never_fabricated_when_not_configured(monkeypatch):
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    result = fetch_nfl_odds_events()
    assert result.events == []
    assert result.source_provenance == NOT_CONFIGURED
    assert result.provider_errors == []


def _fake_event(event_id="evt1"):
    return NormalizedGameOdds(
        provider="sportsgameodds", event_id=event_id, league="NFL", home_team="KC", away_team="BUF",
        game_time_utc="2026-09-13T17:00:00Z", retrieved_at="2026-09-13T12:00:00Z",
        books=[BookLine(book="draftkings", home_moneyline=-150, away_moneyline=130, total=48.5, home_run_line=-2.5)],
    )


def test_fetch_uses_sportsgameodds_when_configured(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "fake_key")
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    monkeypatch.setattr(odds_provider_module, "_fetch_sportsgameodds_nfl_events", lambda: [_fake_event()])

    result = fetch_nfl_odds_events()
    assert result.source_provenance == SPORTSGAMEODDS_CONFIGURED
    assert len(result.events) == 1
    assert result.events[0].event_id == "evt1"


def test_fetch_falls_back_to_theoddsapi_when_sportsgameodds_returns_nothing(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "fake_key")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake_key_2")
    monkeypatch.setattr(odds_provider_module, "_fetch_sportsgameodds_nfl_events", lambda: [])
    monkeypatch.setattr(odds_provider_module, "_fetch_theoddsapi_nfl_events", lambda: [_fake_event("evt2")])

    result = fetch_nfl_odds_events()
    assert result.source_provenance == MULTI_PROVIDER_CONFIGURED
    assert len(result.events) == 1
    assert result.events[0].event_id == "evt2"


def test_fetch_does_not_call_theoddsapi_when_sportsgameodds_already_has_events(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "fake_key")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake_key_2")
    monkeypatch.setattr(odds_provider_module, "_fetch_sportsgameodds_nfl_events", lambda: [_fake_event()])

    def _fail_if_called():
        raise AssertionError("The Odds API should not be called when SportsGameOdds already returned events")

    monkeypatch.setattr(odds_provider_module, "_fetch_theoddsapi_nfl_events", _fail_if_called)
    result = fetch_nfl_odds_events()
    assert len(result.events) == 1


def test_provider_error_is_captured_not_raised(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "fake_key")
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)

    def _raise():
        raise OddsProviderAuthenticationError("SportsGameOdds rejected the configured API key (HTTP 401).")

    monkeypatch.setattr(odds_provider_module, "_fetch_sportsgameodds_nfl_events", _raise)
    result = fetch_nfl_odds_events()
    assert result.events == []
    assert len(result.provider_errors) == 1
    assert "SportsGameOdds" in result.provider_errors[0]
