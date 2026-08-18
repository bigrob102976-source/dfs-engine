"""Milestone 27.3 regression: M27.2's final report incorrectly stated that
native_projections/ "doesn't exist yet". It has existed, been tested, and
been wired into the dashboard optimizer pool since Milestone 23 (commit
77ed8a1) -- this is a deliberately dumb smoke test that guards against that
false claim (or the underlying package actually going missing) ever
recurring silently."""

import importlib


def test_native_projections_package_is_importable():
    pkg = importlib.import_module("native_projections")
    assert pkg is not None


def test_native_projections_version_module_exists():
    version = importlib.import_module("native_projections.version")
    assert version.NATIVE_PROJECTION_MODEL_VERSION


def test_native_projections_core_modules_exist():
    for module_name in (
        "native_projections.hitter_projection",
        "native_projections.pitcher_projection",
        "native_projections.persistence",
        "native_projections.dk_scoring",
        "native_projections.uncertainty",
    ):
        assert importlib.import_module(module_name) is not None
