"""Milestone 32.1, Part 23 -- feature manifest structural tests. Proves
TARGET/HISTORICAL_OUTCOME_ONLY fields cannot accidentally enter a
pregame model feature matrix (the explicit requirement)."""

import pytest

from historical_mlb.manifest import (
    ALWAYS_PREGAME,
    HISTORICAL_OUTCOME_ONLY,
    PREGAME_AFTER_LINEUPS,
    TARGET,
    FeatureDef,
    full_manifest,
    hitter_manifest,
    pitcher_manifest,
    pregame_safe_column_names,
    target_column_names,
)


def test_featuredef_rejects_unknown_availability_class():
    with pytest.raises(ValueError):
        FeatureDef("x", "hitter", "int", "d", "s", "NOT_A_REAL_CLASS", False, "none")


def test_featuredef_rejects_target_flag_without_target_class():
    with pytest.raises(ValueError):
        FeatureDef("x", "hitter", "int", "d", "s", ALWAYS_PREGAME, True, "none")


def test_no_duplicate_field_names_within_hitter_manifest():
    names = [f.name for f in hitter_manifest()]
    assert len(names) == len(set(names))


def test_no_duplicate_field_names_within_pitcher_manifest():
    names = [f.name for f in pitcher_manifest()]
    assert len(names) == len(set(names))


def test_only_actual_dk_points_is_target_for_each_entity():
    assert target_column_names("hitter") == ["actual_dk_points"]
    assert target_column_names("pitcher") == ["actual_dk_points"]


def test_every_actual_prefixed_field_is_outcome_or_target_never_pregame():
    """The core anti-leakage guarantee: any column shaped like an
    observed outcome (actual_*) must NEVER be classified as a pregame
    feature, in either manifest."""
    for f in full_manifest():
        if f.name.startswith("actual_"):
            assert f.availability_class in (HISTORICAL_OUTCOME_ONLY, TARGET), (
                f"{f.name} starts with actual_ but is classified {f.availability_class}"
            )


def test_pregame_safe_column_names_excludes_every_actual_field():
    pre_lineup = set(pregame_safe_column_names("hitter", include_after_lineups=False))
    post_lineup = set(pregame_safe_column_names("hitter", include_after_lineups=True))
    assert not any(c.startswith("actual_") for c in pre_lineup)
    assert not any(c.startswith("actual_") for c in post_lineup)


def test_pre_lineup_excludes_batting_order_and_starter_flag_but_post_lineup_includes_them():
    pre_lineup = set(pregame_safe_column_names("hitter", include_after_lineups=False))
    post_lineup = set(pregame_safe_column_names("hitter", include_after_lineups=True))
    assert "batting_order_actual" not in pre_lineup
    assert "batting_order_actual" in post_lineup

    pre_lineup_p = set(pregame_safe_column_names("pitcher", include_after_lineups=False))
    post_lineup_p = set(pregame_safe_column_names("pitcher", include_after_lineups=True))
    assert "starter_flag" not in pre_lineup_p
    assert "starter_flag" in post_lineup_p


def test_pregame_safe_never_includes_the_target_column():
    for entity in ("hitter", "pitcher"):
        for include_after_lineups in (False, True):
            cols = set(pregame_safe_column_names(entity, include_after_lineups))
            assert "actual_dk_points" not in cols


def test_rolling_features_are_always_pregame():
    for f in hitter_manifest():
        if f.name.startswith("rolling_"):
            assert f.availability_class == ALWAYS_PREGAME
    for f in pitcher_manifest():
        if f.name.startswith("rolling_"):
            assert f.availability_class == ALWAYS_PREGAME
