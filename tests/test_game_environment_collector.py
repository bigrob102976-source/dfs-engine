from research.game_environment import collector
from research.game_environment.bullpen import BullpenProvider, MockBullpenProvider
from research.game_environment.models import BullpenProfile, UmpireProfile, VegasSnapshot, WeatherSnapshot
from research.game_environment.umpires import MockUmpireProvider, UmpireProvider, UnknownUmpireProvider
from research.game_environment.vegas import MockVegasProvider, NotConfiguredVegasProvider, SportsGameOddsVegasProvider, VegasProvider
from research.game_environment.weather import MockWeatherProvider, WeatherProvider


class _NotConfiguredWeatherProvider(WeatherProvider):
    name = "not_configured"
    is_mock = False

    def provider_name(self) -> str:
        return "Not Configured"

    def is_configured(self) -> bool:
        return False

    def get_weather(self, game_id, home_team_abbr, game_datetime_utc, roof) -> WeatherSnapshot:
        raise AssertionError("should never be called when is_configured() is False")


class _NotConfiguredVegasProvider(VegasProvider):
    name = "not_configured"
    is_mock = False

    def provider_name(self) -> str:
        return "Not Configured"

    def is_configured(self) -> bool:
        return False

    def get_vegas_line(self, game_id, home_team_abbr, away_team_abbr, slate_date=None) -> VegasSnapshot:
        raise AssertionError("should never be called when is_configured() is False")


class _NotConfiguredBullpenProvider(BullpenProvider):
    name = "not_configured"
    is_mock = False

    def provider_name(self) -> str:
        return "Not Configured"

    def is_configured(self) -> bool:
        return False

    def get_bullpen(self, team_abbr) -> BullpenProfile:
        raise AssertionError("should never be called when is_configured() is False")


# ----------------------------------------------------------------------------
# Provider resolution
# ----------------------------------------------------------------------------


def test_weather_provider_defaults_to_automatic_mock_fallback(monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    provider, source = collector.get_configured_weather_provider()
    assert isinstance(provider, MockWeatherProvider)
    assert source == "automatic_fallback"


def test_vegas_provider_defaults_to_not_configured_never_silent_mock(monkeypatch):
    """Milestone 24: unlike weather/bullpen, Vegas must NOT silently
    fall back to mock data -- a fake Vegas number is far more likely to
    be trusted and acted on than a missing weather reading."""
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)
    provider, source = collector.get_configured_vegas_provider()
    assert isinstance(provider, NotConfiguredVegasProvider)
    assert provider.is_configured() is False
    assert source == "not_configured"


def test_vegas_provider_uses_mock_only_when_explicitly_requested(monkeypatch):
    monkeypatch.delenv("SPORTSGAMEODDS_API_KEY", raising=False)
    monkeypatch.setenv("GAME_ENVIRONMENT_PROVIDER", "mock")
    provider, source = collector.get_configured_vegas_provider()
    assert isinstance(provider, MockVegasProvider)
    assert source == "explicit_mock"


def test_vegas_provider_uses_real_provider_when_api_key_configured(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "test-key-not-real")
    provider, source = collector.get_configured_vegas_provider()
    assert isinstance(provider, SportsGameOddsVegasProvider)
    assert source == "sportsgameodds_configured"


def test_vegas_provider_prefers_real_key_over_explicit_mock(monkeypatch):
    """SPORTSGAMEODDS_API_KEY always wins, even if GAME_ENVIRONMENT_PROVIDER
    happens to also be set to 'mock' -- a real key configured for
    production should never be silently shadowed by a leftover dev flag."""
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GAME_ENVIRONMENT_PROVIDER", "mock")
    provider, source = collector.get_configured_vegas_provider()
    assert isinstance(provider, SportsGameOddsVegasProvider)
    assert source == "sportsgameodds_configured"


def test_bullpen_provider_defaults_to_automatic_mock_fallback(monkeypatch):
    monkeypatch.delenv("GAME_ENVIRONMENT_PROVIDER", raising=False)
    provider, source = collector.get_configured_bullpen_provider()
    assert isinstance(provider, MockBullpenProvider)
    assert source == "automatic_fallback"


def test_umpire_provider_defaults_to_unknown_never_auto_mock(monkeypatch):
    """Unlike weather/vegas/bullpen, umpire data must never silently
    fall back to mock -- the milestone requires an honest UNKNOWN."""
    monkeypatch.delenv("GAME_ENVIRONMENT_UMPIRE_PROVIDER", raising=False)
    provider, source = collector.get_configured_umpire_provider()
    assert isinstance(provider, UnknownUmpireProvider)
    assert source == "unconfigured"


def test_umpire_provider_uses_mock_when_explicitly_requested(monkeypatch):
    monkeypatch.setenv("GAME_ENVIRONMENT_UMPIRE_PROVIDER", "mock")
    provider, source = collector.get_configured_umpire_provider()
    assert isinstance(provider, MockUmpireProvider)
    assert source == "explicit"


# ----------------------------------------------------------------------------
# build_game_report
# ----------------------------------------------------------------------------


def test_build_game_report_assembles_every_section_with_mock_providers():
    report = collector.build_game_report(
        game_id="g1", home_team="PHI", away_team="COL", game_datetime_utc="2026-08-13T23:00:00Z", venue_name="Citizens Bank Park",
        weather_provider=MockWeatherProvider(), vegas_provider=MockVegasProvider(),
        umpire_provider=MockUmpireProvider(), bullpen_provider=MockBullpenProvider(),
    )
    assert report.weather is not None
    assert report.weather_analysis is not None
    assert report.vegas is not None
    assert report.ballpark is not None
    assert report.umpire.status == "KNOWN"
    assert report.bullpen_home is not None
    assert report.bullpen_away is not None
    assert report.travel_home is not None
    assert report.travel_away is not None
    assert 0.0 <= report.environment_score.overall <= 100.0
    assert report.summary.headline == "COL @ PHI"
    assert report.future_adjustment_preview.enabled is False


def test_build_game_report_degrades_gracefully_with_missing_weather():
    report = collector.build_game_report(
        game_id="g1", home_team="PHI", away_team="COL", game_datetime_utc=None, venue_name=None,
        weather_provider=_NotConfiguredWeatherProvider(), vegas_provider=MockVegasProvider(),
        umpire_provider=UnknownUmpireProvider(), bullpen_provider=MockBullpenProvider(),
    )
    assert report.weather is None
    assert report.weather_analysis is None
    # The rest of the report still builds successfully.
    assert report.vegas is not None
    assert 0.0 <= report.environment_score.overall <= 100.0


def test_build_game_report_degrades_gracefully_with_missing_vegas():
    report = collector.build_game_report(
        game_id="g1", home_team="PHI", away_team="COL", game_datetime_utc=None, venue_name=None,
        weather_provider=MockWeatherProvider(), vegas_provider=_NotConfiguredVegasProvider(),
        umpire_provider=UnknownUmpireProvider(), bullpen_provider=MockBullpenProvider(),
    )
    assert report.vegas is None
    assert report.weather is not None
    assert 0.0 <= report.environment_score.overall <= 100.0


def test_build_game_report_degrades_gracefully_with_missing_umpire():
    report = collector.build_game_report(
        game_id="g1", home_team="PHI", away_team="COL", game_datetime_utc=None, venue_name=None,
        weather_provider=MockWeatherProvider(), vegas_provider=MockVegasProvider(),
        umpire_provider=UnknownUmpireProvider(), bullpen_provider=MockBullpenProvider(),
    )
    assert report.umpire.status == "UNKNOWN"
    # The rest of the report -- crucially, the environment score and
    # summary -- still build successfully without umpire data.
    assert 0.0 <= report.environment_score.overall <= 100.0
    assert report.summary.headline


def test_build_game_report_degrades_gracefully_with_missing_bullpen():
    report = collector.build_game_report(
        game_id="g1", home_team="PHI", away_team="COL", game_datetime_utc=None, venue_name=None,
        weather_provider=MockWeatherProvider(), vegas_provider=MockVegasProvider(),
        umpire_provider=UnknownUmpireProvider(), bullpen_provider=_NotConfiguredBullpenProvider(),
    )
    assert report.bullpen_home is None
    assert report.bullpen_away is None
    assert 0.0 <= report.environment_score.overall <= 100.0


def test_build_game_report_never_touches_an_unknown_ballpark():
    report = collector.build_game_report(
        game_id="g1", home_team="ZZZ", away_team="COL", game_datetime_utc=None, venue_name=None,
        weather_provider=MockWeatherProvider(), vegas_provider=MockVegasProvider(),
        umpire_provider=UnknownUmpireProvider(), bullpen_provider=MockBullpenProvider(),
    )
    assert report.ballpark is None
    # Weather still generates (falls back to an "open" roof assumption
    # when the park itself is unknown), never crashes.
    assert report.weather is not None
