"""End-to-end tests for SportsGameOddsVegasProvider -- the conversion
from a fake OddsProvider's normalized events into ONE real VegasSnapshot
(consensus + implied runs + provenance + first-observed history), all
without touching the network (a fake OddsProvider stands in)."""

import pytest

from research.game_environment.providers.base import OddsProvider
from research.game_environment.providers.models import BookLine, NormalizedGameOdds
from research.game_environment.vegas import (
    NotConfiguredVegasProvider,
    SportsGameOddsVegasProvider,
    VegasProviderNotConfiguredError,
    VegasProviderUnavailableError,
)
from research.game_environment import storage as ge_storage


class FakeOddsProvider(OddsProvider):
    name = "fake"
    is_mock = False

    def __init__(self, events=None, configured=True, error=None):
        self._events = events or []
        self._configured = configured
        self._error = error
        self.call_count = 0

    def provider_name(self):
        return "Fake"

    def is_configured(self):
        return self._configured

    def get_odds(self, league, date):
        self.call_count += 1
        if self._error:
            raise self._error
        return self._events


def make_event(**overrides):
    defaults = dict(
        provider="sportsgameodds", event_id="evt_1", league="MLB",
        home_team="LAD", away_team="SD", game_time_utc="2026-08-17T23:10:00Z",
        retrieved_at="2026-08-17T18:00:00+00:00",
        books=[
            BookLine(book="draftkings", home_moneyline=-165, away_moneyline=140, total=8.5, home_run_line=-1.5, away_run_line=1.5),
            BookLine(book="fanduel", home_moneyline=-160, away_moneyline=135, total=8.5),
        ],
    )
    defaults.update(overrides)
    return NormalizedGameOdds(**defaults)


# ----------------------------------------------------------------------------
# Basic conversion
# ----------------------------------------------------------------------------


def test_provider_name_and_not_mock():
    provider = SportsGameOddsVegasProvider(FakeOddsProvider())
    assert provider.provider_name() == "SportsGameOdds"
    assert provider.is_mock is False


def test_is_configured_delegates_to_underlying_odds_provider():
    assert SportsGameOddsVegasProvider(FakeOddsProvider(configured=True)).is_configured() is True
    assert SportsGameOddsVegasProvider(FakeOddsProvider(configured=False)).is_configured() is False


def test_get_vegas_line_returns_real_consensus_and_implied_runs(tmp_path):
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")

    assert snapshot.is_mock is False
    assert snapshot.provider_name == "SportsGameOdds"
    assert snapshot.event_id == "evt_1"
    assert snapshot.current_home.total == 8.5
    assert snapshot.home_implied_runs == 5.0  # 8.5/2 + 1.5/2
    assert snapshot.away_implied_runs == 3.5
    assert snapshot.implied_runs_is_valid is True
    assert snapshot.implied_runs_calculation_method == "run_line_split_of_consensus_total"
    assert set(snapshot.books_used) == {"draftkings", "fanduel"}
    assert len(snapshot.books) == 2


def test_first_pull_of_day_uses_current_as_opening(tmp_path):
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")

    assert snapshot.is_first_pull_of_day is True
    assert snapshot.opening_home.total == snapshot.current_home.total
    assert snapshot.total_movement == 0.0


def test_second_pull_uses_first_saved_snapshot_as_opening(tmp_path):

    # Simulate an earlier real snapshot already saved today with a lower total.
    earlier_doc = {
        "slate_date": "2026-08-17", "generated_at": "2026-08-17T14:00:00+00:00",
        "games": [
            {
                "game_id": "g1",
                "vegas": {
                    "is_mock": False,
                    "current_home": {"moneyline": -150, "run_line": -1.5, "run_line_odds": None, "total": 8.0},
                    "current_away": {"moneyline": 130, "run_line": 1.5, "run_line_odds": None, "total": 8.0},
                    "game_status": "PREGAME",
                },
            }
        ],
    }
    ge_storage.save_environment_report(earlier_doc, output_root=tmp_path)

    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")

    assert snapshot.is_first_pull_of_day is False
    assert snapshot.opening_home.total == 8.0  # from the earlier snapshot
    assert snapshot.current_home.total == 8.5  # from this pull
    assert snapshot.total_movement == 0.5


def test_ignores_mock_snapshots_when_resolving_first_observed(tmp_path):
    mock_doc = {
        "slate_date": "2026-08-17", "generated_at": "2026-08-17T10:00:00+00:00",
        "games": [{"game_id": "g1", "vegas": {"is_mock": True, "current_home": {"total": 99.0}, "current_away": {"total": 99.0}}}],
    }
    ge_storage.save_environment_report(mock_doc, output_root=tmp_path)

    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event()]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")

    # A prior MOCK snapshot must never be used as the real "first observed" baseline.
    assert snapshot.is_first_pull_of_day is True
    assert snapshot.opening_home.total == 8.5


# ----------------------------------------------------------------------------
# No matching event / failure translation
# ----------------------------------------------------------------------------


def test_no_matching_event_raises_unavailable():
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[make_event(home_team="NYY", away_team="BOS")]))
    with pytest.raises(VegasProviderUnavailableError):
        provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")


def test_underlying_not_configured_error_translates_to_vegas_not_configured():
    from research.game_environment.providers.base import OddsProviderNotConfiguredError

    provider = SportsGameOddsVegasProvider(FakeOddsProvider(error=OddsProviderNotConfiguredError("no key")))
    with pytest.raises(VegasProviderNotConfiguredError):
        provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")


def test_underlying_rate_limit_error_translates_to_vegas_unavailable():
    from research.game_environment.providers.base import OddsProviderRateLimitedError

    provider = SportsGameOddsVegasProvider(FakeOddsProvider(error=OddsProviderRateLimitedError("429")))
    with pytest.raises(VegasProviderUnavailableError):
        provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")


def test_underlying_auth_error_translates_to_vegas_unavailable():
    from research.game_environment.providers.base import OddsProviderAuthenticationError

    provider = SportsGameOddsVegasProvider(FakeOddsProvider(error=OddsProviderAuthenticationError("401")))
    with pytest.raises(VegasProviderUnavailableError):
        provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")


# ----------------------------------------------------------------------------
# Process-local memoization: one game report loop shouldn't re-fetch events
# ----------------------------------------------------------------------------


def test_multiple_games_same_date_share_one_underlying_fetch(tmp_path):
    fake = FakeOddsProvider(events=[make_event(), make_event(event_id="evt_2", home_team="NYY", away_team="BOS")])
    provider = SportsGameOddsVegasProvider(fake, snapshot_root=tmp_path)

    provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    provider.get_vegas_line("g2", "NYY", "BOS", slate_date="2026-08-17", mlb_game_status="Scheduled")

    assert fake.call_count == 1


# ----------------------------------------------------------------------------
# Invalid calculation -> None + warnings surfaced on the snapshot
# ----------------------------------------------------------------------------


def test_no_run_line_available_gives_none_implied_runs_with_warning(tmp_path):
    event = make_event(books=[BookLine(book="draftkings", home_moneyline=-165, away_moneyline=140, total=8.5)])
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[event]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line("g1", "LAD", "SD", slate_date="2026-08-17", mlb_game_status="Scheduled")

    assert snapshot.home_implied_runs is None
    assert snapshot.away_implied_runs is None
    assert snapshot.implied_runs_is_valid is False
    assert any("run line" in w.lower() for w in snapshot.validation_warnings)


# ----------------------------------------------------------------------------
# NotConfiguredVegasProvider
# ----------------------------------------------------------------------------


def test_not_configured_provider_is_never_configured():
    provider = NotConfiguredVegasProvider()
    assert provider.is_configured() is False
    assert provider.is_mock is False


def test_not_configured_provider_raises_if_called_directly():
    provider = NotConfiguredVegasProvider()
    with pytest.raises(VegasProviderNotConfiguredError):
        provider.get_vegas_line("g1", "LAD", "SD")
