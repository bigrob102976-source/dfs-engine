"""NFL M4 -- targeted tests for nfl/projection_provider.py."""

import pytest

from nfl.projection_provider import BigMoneyNativeNflProvider, NflProjectionProviderNotConfiguredError


def test_big_money_native_reports_not_configured():
    provider = BigMoneyNativeNflProvider()
    assert provider.is_configured() is False
    assert provider.provider_name() == "Big Money Native"


def test_big_money_native_get_projections_raises_not_fabricates():
    """The honest M4 behavior: no real model exists yet, so this must
    raise -- never return an empty-but-successful list, never return a
    fabricated/zero projection."""
    provider = BigMoneyNativeNflProvider()
    with pytest.raises(NflProjectionProviderNotConfiguredError):
        provider.get_projections(151307, "2026-09-13")


def test_provider_version_reflects_constructor_arg():
    provider = BigMoneyNativeNflProvider(model_version="v0.1.0")
    assert provider.provider_version() == "v0.1.0"
    assert BigMoneyNativeNflProvider().provider_version() is None
