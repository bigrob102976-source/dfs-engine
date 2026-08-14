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


def test_registry_resolves_bluecollar_but_it_stays_unconfigured(monkeypatch):
    """Explicitly naming bluecollar resolves the CLASS (source=explicit)
    but the provider itself must still report is_configured() == False
    -- the registry cannot make BlueCollar usable early."""
    monkeypatch.setenv("EXTERNAL_PROJECTION_PROVIDER", "bluecollar")
    provider, reason, source = get_configured_provider()
    assert provider is not None
    assert source == "explicit"
    assert reason is None
    assert provider.is_configured() is False


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
# BlueCollar disabled placeholder
# ----------------------------------------------------------------------------


def test_bluecollar_is_configured_is_false_even_with_env_vars_set(monkeypatch):
    """Even if a user sets both env vars, is_configured() must stay
    False -- there is no documented API contract to call yet."""
    monkeypatch.setenv("BLUECOLLAR_API_KEY", "fake-key-for-test")
    monkeypatch.setenv("BLUECOLLAR_API_BASE_URL", "https://example.invalid/api")
    assert BlueCollarProvider().is_configured() is False


def test_bluecollar_list_slates_raises_not_configured_never_network():
    provider = BlueCollarProvider()
    with pytest.raises(ProjectionProviderNotConfiguredError) as exc_info:
        provider.list_slates("2026-08-13")
    assert "documentation" in str(exc_info.value).lower() or "credentials" in str(exc_info.value).lower()


def test_bluecollar_get_projections_raises_not_configured_never_network():
    provider = BlueCollarProvider()
    with pytest.raises(ProjectionProviderNotConfiguredError):
        provider.get_projections("any-slate-id")


def test_bluecollar_provider_name_and_no_network_imports():
    provider = BlueCollarProvider()
    assert provider.provider_name() == "BlueCollar DFS"
    import external_projections.bluecollar_provider as module

    # Never import an HTTP client -- this provider makes no network calls at all.
    for banned in ("requests", "httpx", "urllib.request", "aiohttp"):
        assert banned not in module.__dict__, f"BlueCollarProvider must not import {banned}"
