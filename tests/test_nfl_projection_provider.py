"""NFL M4/M10 -- targeted tests for nfl/projection_provider.py. Uses a
tmp_path artifact root throughout so these tests never depend on (or
are broken by) real trained models actually being present on disk."""

import json
from pathlib import Path

import joblib
import pytest

from nfl.projection_provider import BigMoneyNativeNflProvider, NflProjectionProviderNotConfiguredError


def test_not_configured_when_no_artifacts_exist(tmp_path):
    provider = BigMoneyNativeNflProvider(artifact_root=tmp_path)
    assert provider.is_configured() is False
    assert provider.provider_name() == "Big Money Native"


def test_get_projections_raises_not_fabricates_when_not_configured(tmp_path):
    """The honest behavior when no real model exists: raise -- never
    return an empty-but-successful list, never a fabricated/zero
    projection."""
    provider = BigMoneyNativeNflProvider(artifact_root=tmp_path)
    with pytest.raises(NflProjectionProviderNotConfiguredError):
        provider.get_projections(151307, "2026-09-13")


def test_configured_when_at_least_one_position_model_exists(tmp_path):
    model_dir = tmp_path / "qb" / "v1"
    model_dir.mkdir(parents=True)
    joblib.dump({"fake": "pipeline"}, model_dir / "model.joblib")
    provider = BigMoneyNativeNflProvider(artifact_root=tmp_path)
    assert provider.is_configured() is True


def test_provider_version_defaults_to_model_version(tmp_path):
    from historical_models.nfl_v1.config import MODEL_VERSION
    provider = BigMoneyNativeNflProvider(artifact_root=tmp_path)
    assert provider.provider_version() == MODEL_VERSION


def test_provider_version_reflects_constructor_arg(tmp_path):
    provider = BigMoneyNativeNflProvider(model_version="v0.1.0", artifact_root=tmp_path)
    assert provider.provider_version() == "v0.1.0"
