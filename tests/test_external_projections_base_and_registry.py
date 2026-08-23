import pytest

from external_projections.base import (
    ProjectionProvider,
    ProjectionProviderNotConfiguredError,
)
from external_projections.bluecollar_provider import BlueCollarProvider
from external_projections.mock_provider import MockExternalProvider
from external_projections.registry import PROVIDER_FACTORIES, get_configured_provider

# ----------------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------------


def test_base_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ProjectionProvider()


def test_mock_provider_implements_interface():
    assert isinstance(MockExternalProvider(), ProjectionProvider)


def test_bluecollar_provider_implements_interface():
    assert isinstance(BlueCollarProvider(), ProjectionProvider)


# ----------------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------------


def test_registry_default_is_unconfigured_not_mock(monkeypatch):
    """Unlike the DFS salary provider, there is NO automatic mock
    fallback -- external projections are purely additive."""
    monkeypatch.delenv("EXTERNAL_PROJECTION_PROVIDER", raising=False)
    provider, reason, source = get_configured_provider()
    assert provider is None
    assert reason is None
    assert source == "unconfigured"


def test_registry_whitespace_only_is_unconfigured(monkeypatch):
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "   ")
    provider, reason, source = get_configured_provider()
    assert provider is None
    assert source == "unconfigured"


def test_registry_resolves_explicit_mock(monkeypatch):
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "mock")
    provider, reason, source = get_configured_provider()
    assert provider is not None
    assert provider.name == "mock_external_projections"
    assert reason is None
    assert source == "explicit"


def test_registry_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "MOCK")
    provider, _reason, source = get_configured_provider()
    assert provider is not None
    assert source == "explicit"


def test_registry_resolves_bluecollar_unconfigured_with_no_api_key(monkeypatch):
    """Explicitly naming bluecollar resolves the CLASS (source=explicit)
    but the provider itself must still report is_configured() == False
    when BLUECOLLAR_API_KEY isn't set -- the registry alone cannot make
    BlueCollar usable."""
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "bluecollar")
    monkeypatch.delenv("BLUECOLLAR_API_KEY", raising=False)
    provider, reason, source = get_configured_provider()
    assert provider is not None
    assert source == "explicit"
    assert reason is None
    assert provider.is_configured() is False


def test_registry_resolves_bluecollar_configured_once_api_key_is_set(monkeypatch):
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "bluecollar")
    monkeypatch.setenv("BLUECOLLAR_API_KEY", "fake-key-for-test")
    provider, _reason, source = get_configured_provider()
    assert provider is not None
    assert source == "explicit"
    assert provider.is_configured() is True


def test_registry_reports_unknown_provider_name(monkeypatch):
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "sportsdataio")
    provider, reason, source = get_configured_provider()
    assert provider is None
    assert "not a recognized provider" in reason
    assert "sportsdataio" in reason
    assert source == "unknown"


def test_registry_never_raises(monkeypatch):
    monkeypatch.delenv("EXTERNAL_PROJECTION_PROVIDER", raising=False)
    get_configured_provider()
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "totally-unknown")
    get_configured_provider()


def test_provider_factories_contains_mock_and_bluecollar():
    assert set(PROVIDER_FACTORIES) == {"mock", "bluecollar"}


# ----------------------------------------------------------------------------
# BlueCollar -- real provider, unconfigured state (no API key)
# ----------------------------------------------------------------------------


def test_bluecollar_is_configured_is_false_with_no_api_key(monkeypatch):
    monkeypatch.delenv("BLUECOLLAR_API_KEY", raising=False)
    assert BlueCollarProvider().is_configured() is False


def test_bluecollar_is_configured_is_true_once_api_key_is_set():
    assert BlueCollarProvider(api_key="fake-key-for-test").is_configured() is True


def test_bluecollar_list_slates_raises_not_configured_never_network_when_no_key(tmp_path, monkeypatch):
    # Isolated cache_root -- avoids reading a real cached response from
    # an earlier, properly-authenticated fetch on disk (data/cache/bluecollar/).
    # Also explicitly delenv BLUECOLLAR_API_KEY: some other provider module
    # (e.g. research/game_environment/providers/theoddsapi.py) calls
    # config.env_loader.load_dashboard_env() at IMPORT time, which loads
    # dashboard/.env.local straight into os.environ for the rest of the
    # pytest session (a raw os.environ mutation, not monkeypatch-reverted)
    # -- constructing BlueCollarProvider(api_key=None) alone is not
    # enough to guarantee "no key" once a real key exists in .env.local.
    monkeypatch.delenv("BLUECOLLAR_API_KEY", raising=False)
    provider = BlueCollarProvider(api_key=None, cache_root=tmp_path)
    with pytest.raises(ProjectionProviderNotConfiguredError) as exc_info:
        provider.list_slates("2026-08-13")
    assert "BLUECOLLAR_API_KEY" in str(exc_info.value)


def test_bluecollar_get_projections_raises_not_configured_never_network_when_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("BLUECOLLAR_API_KEY", raising=False)
    provider = BlueCollarProvider(api_key=None, cache_root=tmp_path)
    with pytest.raises(ProjectionProviderNotConfiguredError):
        provider.get_projections("bluecollar-2026-08-13-0-main")


def test_bluecollar_provider_name():
    assert BlueCollarProvider().provider_name() == "BlueCollar DFS"


def test_bluecollar_exception_messages_never_contain_the_api_key():
    """The one hard security invariant: whatever goes wrong, the
    configured key must never appear in an exception's message."""
    secret = "sk-super-secret-value-12345"
    provider = BlueCollarProvider(api_key=None)
    try:
        provider.list_slates("2026-08-13")
    except ProjectionProviderNotConfiguredError as exc:
        assert secret not in str(exc)
