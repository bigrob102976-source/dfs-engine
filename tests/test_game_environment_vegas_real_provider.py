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


# ----------------------------------------------------------------------------
# Milestone 27.1 -- end-to-end event resolution + impossible-state guard,
# through the REAL SportsGameOddsVegasProvider.get_vegas_line() pipeline
# (not just the resolver/guard in isolation). Regression fixture modeled
# exactly on the confirmed 2026-08-18 LAD @ COL bug.
# ----------------------------------------------------------------------------


def test_lad_col_regression_end_to_end_resolves_todays_pregame_event(tmp_path):
    # Scheduled far in the future (relative to whenever this suite
    # actually runs) so the impossible-state guard is deterministically
    # applicable regardless of the real wall clock -- get_vegas_line()'s
    # public signature has no now_utc override, so this test relies on
    # "now" always being before this fixture's scheduled start.
    game_a_yesterday = make_event(
        event_id="evt_yesterday", home_team="COL", away_team="LAD", game_time_utc="2099-08-18T00:40:00.000Z",
        event_status={"started": True, "live": True, "ended": False, "completed": False},
    )
    game_b_today = make_event(
        event_id="evt_today", home_team="COL", away_team="LAD", game_time_utc="2099-08-19T00:40:00.000Z",
        event_status={"started": False, "live": False, "ended": False, "completed": False},
        books=[BookLine(book="draftkings", home_moneyline=200, away_moneyline=-250, total=9.5, home_run_line=1.5, away_run_line=-1.5)],
    )
    game_c_tomorrow = make_event(event_id="evt_tomorrow", home_team="COL", away_team="LAD", game_time_utc="2099-08-20T00:40:00.000Z")

    provider = SportsGameOddsVegasProvider(
        FakeOddsProvider(events=[game_a_yesterday, game_b_today, game_c_tomorrow]), snapshot_root=tmp_path
    )
    snapshot = provider.get_vegas_line(
        "824319", "COL", "LAD", slate_date="2099-08-18", mlb_game_status="Scheduled",
        mlb_scheduled_start_utc="2099-08-19T00:40:00Z",
    )

    assert snapshot.event_id == "evt_today"
    assert snapshot.event_id != "evt_yesterday"
    assert snapshot.game_status == "PREGAME"
    assert snapshot.vegas_projection_status == "LIVE_PREGAME"
    assert snapshot.current_home.total == 9.5


def test_future_game_cannot_become_in_play_from_mismatched_provider_event(tmp_path):
    # A provider feed that ONLY contains the wrong (out-of-tolerance) day's
    # event can never be silently accepted as "close enough" just because
    # the teams match -- the event resolver itself rejects it as
    # NOT_MATCHED (a real gap, not a wrong-day guess) before the game ever
    # has a chance to be misclassified IN_PLAY from mismatched provider data.
    game_a_yesterday = make_event(
        event_id="evt_yesterday", home_team="COL", away_team="LAD", game_time_utc="2099-08-18T00:40:00.000Z",
        event_status={"started": True, "live": True, "ended": False, "completed": False},
    )
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[game_a_yesterday]), snapshot_root=tmp_path)
    with pytest.raises(VegasProviderUnavailableError):
        provider.get_vegas_line(
            "824319", "COL", "LAD", slate_date="2099-08-18", mlb_game_status="Scheduled",
            mlb_scheduled_start_utc="2099-08-19T00:40:00Z",
        )


def test_wrong_day_event_rejected_ambiguity_falls_back_or_errors(tmp_path):
    events = [
        make_event(event_id="evt_yesterday", home_team="COL", away_team="LAD", game_time_utc="2026-08-18T00:40:00.000Z"),
        make_event(event_id="evt_tomorrow", home_team="COL", away_team="LAD", game_time_utc="2026-08-20T00:40:00.000Z"),
    ]
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=events), snapshot_root=tmp_path)
    # Neither candidate is within tolerance of today's actual scheduled
    # start -- NOT_MATCHED, never a wrong-day guess.
    with pytest.raises(VegasProviderUnavailableError):
        provider._fetch_and_build_current(  # noqa: SLF001 -- exercising the raise path directly
            "824319", "COL", "LAD", "2026-08-18", "Scheduled", "2026-08-19T00:40:00Z"
        )


def test_same_day_doubleheader_ambiguous_events_raise_unavailable(tmp_path):
    events = [
        make_event(event_id="evt_g1", home_team="CHC", away_team="STL", game_time_utc="2026-08-18T18:05:00Z"),
        make_event(event_id="evt_g2", home_team="CHC", away_team="STL", game_time_utc="2026-08-18T21:00:00Z"),
    ]
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=events), snapshot_root=tmp_path)
    with pytest.raises(VegasProviderUnavailableError, match="ambiguous"):
        provider._fetch_and_build_current(  # noqa: SLF001
            "g1", "CHC", "STL", "2026-08-18", "Scheduled", "2026-08-18T19:30:00Z"
        )


def test_provider_status_conflict_flag_set_when_guard_fires(tmp_path):
    game_today_but_reported_in_play = make_event(
        event_id="evt_today", home_team="COL", away_team="LAD", game_time_utc="2099-08-19T00:40:00.000Z",
        event_status={"started": True, "live": True, "ended": False, "completed": False},
        books=[BookLine(book="draftkings", home_moneyline=200, away_moneyline=-250, total=9.5, home_run_line=1.5, away_run_line=-1.5)],
    )
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[game_today_but_reported_in_play]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line(
        "824319", "COL", "LAD", slate_date="2099-08-18", mlb_game_status="Scheduled",
        mlb_scheduled_start_utc="2099-08-19T00:40:00Z",
    )
    assert snapshot.provider_status_conflict is True
    assert snapshot.game_status == "PREGAME"
    # Even a provider falsely claiming in-play must never suppress the
    # actual real market data that WAS returned for the correctly-matched event.
    assert snapshot.current_home.total == 9.5
    assert snapshot.vegas_projection_status == "LIVE_PREGAME"


def test_status_override_correctly_applies_once_scheduled_start_has_passed(tmp_path):
    # Uses a scheduled start comfortably in the past (relative to whenever
    # this test actually runs) so "now" (the real wall clock, since
    # get_vegas_line()'s public signature doesn't expose overriding it)
    # is always safely after it -- the guard must never fire here.
    game_now_live = make_event(
        event_id="evt_past", home_team="COL", away_team="LAD", game_time_utc="2020-01-01T00:40:00.000Z",
        event_status={"started": True, "live": True, "ended": False, "completed": False},
    )
    provider = SportsGameOddsVegasProvider(FakeOddsProvider(events=[game_now_live]), snapshot_root=tmp_path)
    snapshot = provider.get_vegas_line(
        "824319", "COL", "LAD", slate_date="2020-01-01", mlb_game_status="Scheduled",
        mlb_scheduled_start_utc="2020-01-01T00:40:00Z",
    )
    assert snapshot.game_status == "IN_PLAY"
    assert snapshot.provider_status_conflict is False
