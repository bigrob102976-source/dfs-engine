"""Milestone 27 -- MultiProviderVegasProvider: SportsGameOdds PRIMARY,
The Odds API SECONDARY/fallback. Every test uses fake OddsProvider
instances (no network), mirroring
tests/test_game_environment_vegas_real_provider.py's exact pattern."""

from research.game_environment.providers.base import (
    OddsProvider,
    OddsProviderRateLimitedError,
    OddsProviderUnavailableError,
)
from research.game_environment.providers.coverage import (
    EVENT_NOT_MATCHED,
    NOT_CONFIGURED,
    PLAN_RESTRICTED,
    PREGAME_NOT_AVAILABLE,
    VALID,
)
from research.game_environment.providers.models import BookLine, NormalizedGameOdds
from research.game_environment.vegas import (
    MultiProviderVegasProvider,
    SportsGameOddsVegasProvider,
    TheOddsAPIVegasProvider,
)


class FakeOddsProvider(OddsProvider):
    name = "fake"
    is_mock = False

    def __init__(self, label, events=None, configured=True, error=None):
        self._label = label
        self._events = events or []
        self._configured = configured
        self._error = error
        self.call_count = 0

    def provider_name(self):
        return self._label

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
        home_team="COL", away_team="LAD", game_time_utc="2026-08-17T23:10:00Z",
        retrieved_at="2026-08-17T18:00:00+00:00",
        books=[BookLine(book="draftkings", home_moneyline=200, away_moneyline=-250, total=12.5, home_run_line=1.5, away_run_line=-1.5)],
    )
    defaults.update(overrides)
    return NormalizedGameOdds(**defaults)


def _providers(primary_events=None, primary_configured=True, primary_error=None, secondary_events=None, secondary_configured=True, secondary_error=None, has_secondary=True, tmp_path=None):
    primary = SportsGameOddsVegasProvider(FakeOddsProvider("SportsGameOdds", events=primary_events, configured=primary_configured, error=primary_error), snapshot_root=tmp_path)
    secondary = None
    if has_secondary:
        secondary = TheOddsAPIVegasProvider(FakeOddsProvider("The Odds API", events=secondary_events, configured=secondary_configured, error=secondary_error), snapshot_root=tmp_path)
    return MultiProviderVegasProvider(primary, secondary, snapshot_root=tmp_path)


# ---------------------------------------------------------------------------
# Primary selection
# ---------------------------------------------------------------------------


def test_primary_selected_when_valid(tmp_path):
    provider = _providers(primary_events=[make_event()], secondary_events=[make_event(event_id="evt_2")], tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.selected_provider == "SportsGameOdds"
    assert snap.fallback_used is False
    assert snap.primary_provider_status == VALID
    assert snap.current_home.total == 12.5


def test_primary_valid_beats_secondary_never_blended(tmp_path):
    # Secondary has a DIFFERENT total -- must never leak into the result.
    provider = _providers(
        primary_events=[make_event(books=[BookLine(book="dk", home_moneyline=200, away_moneyline=-250, total=12.5, home_run_line=1.5, away_run_line=-1.5)])],
        secondary_events=[make_event(provider="theoddsapi", books=[BookLine(book="fd", home_moneyline=180, away_moneyline=-220, total=9.0, home_run_line=1.0, away_run_line=-1.0)])],
        tmp_path=tmp_path,
    )
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.current_home.total == 12.5  # primary's number, not secondary's
    assert snap.selected_provider == "SportsGameOdds"


# ---------------------------------------------------------------------------
# Secondary fallback
# ---------------------------------------------------------------------------


def test_primary_event_not_matched_uses_secondary(tmp_path):
    provider = _providers(primary_events=[], secondary_events=[make_event(provider="theoddsapi")], tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.selected_provider == "The Odds API"
    assert snap.fallback_used is True
    assert snap.primary_provider_status == EVENT_NOT_MATCHED
    assert snap.secondary_provider_status == VALID
    assert snap.current_home.total == 12.5


def test_primary_no_total_uses_secondary(tmp_path):
    no_total_event = make_event(books=[BookLine(book="dk", home_moneyline=200, away_moneyline=-250)])  # no total
    provider = _providers(primary_events=[no_total_event], secondary_events=[make_event(provider="theoddsapi")], tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.fallback_used is True
    assert snap.selected_provider == "The Odds API"
    assert snap.primary_provider_status == "EVENT_MATCHED_NO_TOTAL"


def test_primary_rate_limited_uses_secondary(tmp_path):
    provider = _providers(primary_error=OddsProviderRateLimitedError("rate limit exceeded"), secondary_events=[make_event(provider="theoddsapi")], tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.primary_provider_status == PLAN_RESTRICTED
    assert snap.selected_provider == "The Odds API"
    assert snap.fallback_used is True


# ---------------------------------------------------------------------------
# Both missing => zero Vegas contribution
# ---------------------------------------------------------------------------


def test_both_providers_missing_yields_zero_contribution_not_fabricated(tmp_path):
    provider = _providers(primary_events=[], secondary_events=[], tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.current_home.total is None
    assert snap.home_implied_runs is None
    assert snap.away_implied_runs is None
    assert snap.implied_runs_is_valid is False
    assert snap.selected_provider is None
    assert snap.missing_reason == EVENT_NOT_MATCHED
    assert snap.vegas_projection_status == "MISSING"


def test_no_secondary_configured_is_honestly_not_configured(tmp_path):
    provider = _providers(primary_events=[], has_secondary=False, tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.secondary_provider_status == NOT_CONFIGURED
    assert snap.selected_provider is None


# ---------------------------------------------------------------------------
# Provider provenance always recorded
# ---------------------------------------------------------------------------


def test_provenance_fields_always_populated_even_when_missing(tmp_path):
    provider = _providers(primary_events=[], secondary_events=[], tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.primary_provider_status is not None
    assert snap.secondary_provider_status is not None
    assert snap.missing_reason is not None


# ---------------------------------------------------------------------------
# Pregame gating applies to the secondary provider too
# ---------------------------------------------------------------------------


def test_secondary_never_used_when_game_is_in_play(tmp_path):
    provider = _providers(primary_events=[make_event()], secondary_events=[make_event(provider="theoddsapi")], tmp_path=tmp_path)
    # No prior pregame snapshot saved -> in-play/final games can't use ANY
    # current fetch, from either provider (pregame lock is authoritative).
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="In Progress")
    assert snap.game_status == "IN_PLAY"
    assert snap.selected_provider is None
    assert snap.vegas_projection_status == "IN_PLAY_ONLY"


def test_secondary_pregame_not_available_classification(tmp_path):
    # Primary matched but game already final -- classified PREGAME_NOT_AVAILABLE, not silently treated as missing-total.
    provider = _providers(primary_events=[make_event()], has_secondary=False, tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Final")
    assert snap.primary_provider_status == PREGAME_NOT_AVAILABLE


# ---------------------------------------------------------------------------
# LAD/COL-style reconciliation (synthetic, mirrors the real live-validation shape)
# ---------------------------------------------------------------------------


def test_lad_col_style_implied_runs_reconcile_with_total(tmp_path):
    provider = _providers(primary_events=[make_event()], tmp_path=tmp_path)
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert round((snap.home_implied_runs or 0) + (snap.away_implied_runs or 0), 2) == snap.current_home.total


def test_is_configured_true_when_only_secondary_configured(tmp_path):
    provider = _providers(primary_configured=False, primary_events=[], secondary_events=[make_event(provider="theoddsapi")], tmp_path=tmp_path)
    assert provider.is_configured() is True
    snap = provider.get_vegas_line("g1", "COL", "LAD", slate_date="2026-08-17", mlb_game_status="Scheduled")
    assert snap.selected_provider == "The Odds API"


def test_neither_configured_is_not_configured():
    provider = _providers(primary_configured=False, has_secondary=False)
    assert provider.is_configured() is False
