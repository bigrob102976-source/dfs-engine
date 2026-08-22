"""Milestone 32.2 -- feature allowlist / leakage-guard tests for
historical_models.pitcher_v1.features. FEATURE_COLUMNS is derived
directly from historical_mlb.manifest.pitcher_manifest() at import
time, so most of these assert against the manifest itself rather than
any synthetic DataFrame."""

import pandas as pd
import pytest

from historical_mlb.manifest import HISTORICAL_OUTCOME_ONLY, TARGET, pitcher_manifest
from historical_models.pitcher_v1.features import (
    CATEGORICAL_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    assert_no_leakage,
    build_feature_audit,
)


def test_feature_columns_is_union_of_numeric_and_categorical():
    assert set(FEATURE_COLUMNS) == set(NUMERIC_FEATURE_COLUMNS) | set(CATEGORICAL_FEATURE_COLUMNS)
    assert len(FEATURE_COLUMNS) == len(NUMERIC_FEATURE_COLUMNS) + len(CATEGORICAL_FEATURE_COLUMNS)


def test_every_feature_column_is_always_pregame_in_the_manifest():
    manifest_by_name = {f.name: f for f in pitcher_manifest()}
    for column in FEATURE_COLUMNS:
        f = manifest_by_name.get(column)
        assert f is not None, f"{column} is not in pitcher_manifest() at all"
        assert f.availability_class == "ALWAYS_PREGAME", f"{column} is {f.availability_class}, not ALWAYS_PREGAME"


def test_target_column_never_in_feature_columns():
    target_names = {f.name for f in pitcher_manifest() if f.availability_class == TARGET}
    assert "actual_dk_points" in target_names
    assert not (target_names & set(FEATURE_COLUMNS))


def test_no_actual_prefixed_column_in_feature_columns():
    assert not any(c.startswith("actual_") for c in FEATURE_COLUMNS)


def test_historical_outcome_only_columns_never_in_feature_columns():
    outcome_only = {f.name for f in pitcher_manifest() if f.availability_class == HISTORICAL_OUTCOME_ONLY}
    assert not (outcome_only & set(FEATURE_COLUMNS))


def test_salary_and_vegas_never_in_feature_columns():
    for forbidden in ("draftkings_salary", "vegas_moneyline", "vegas_total"):
        assert forbidden not in FEATURE_COLUMNS


def test_player_identity_never_one_hot_encoded():
    """Explicit instruction: 'Do NOT one-hot player ID as a shortcut.'"""
    assert "player_id" not in FEATURE_COLUMNS
    assert "player_name" not in FEATURE_COLUMNS


def test_assert_no_leakage_passes_on_real_feature_columns():
    assert_no_leakage(FEATURE_COLUMNS)  # must not raise


@pytest.mark.parametrize("forbidden_column", ["actual_dk_points", "actual_pitch_count", "target_points", "result_flag", "final_score", "postgame_notes"])
def test_assert_no_leakage_rejects_forbidden_columns(forbidden_column):
    with pytest.raises(ValueError):
        assert_no_leakage(FEATURE_COLUMNS + [forbidden_column])


def test_assert_no_leakage_rejects_salary_and_vegas():
    for forbidden in ("draftkings_salary", "vegas_moneyline", "vegas_total"):
        with pytest.raises(ValueError):
            assert_no_leakage(FEATURE_COLUMNS + [forbidden])


def test_build_feature_audit_marks_target_and_included_columns_correctly():
    df = pd.DataFrame({
        "actual_dk_points": [10.0, 12.0],
        FEATURE_COLUMNS[0]: [1.0, 2.0],
        "draftkings_salary": [None, None],
        "starter_flag": [True, True],
        "not_a_real_column_xyz": [1, 2],
    })
    audit = build_feature_audit(df)
    by_column = {row.column: row for row in audit}

    assert by_column["actual_dk_points"].included is False
    assert "TARGET" in by_column["actual_dk_points"].reason

    assert by_column[FEATURE_COLUMNS[0]].included is True

    assert by_column["draftkings_salary"].included is False
    assert "unavailable" in by_column["draftkings_salary"].reason.lower()

    assert by_column["starter_flag"].included is False
    assert by_column["not_a_real_column_xyz"].included is False
    assert "not in the pitcher feature manifest" in by_column["not_a_real_column_xyz"].reason


def test_build_feature_audit_covers_every_dataframe_column_exactly_once():
    df = pd.DataFrame({col: [1.0, 2.0] for col in FEATURE_COLUMNS[:5]})
    audit = build_feature_audit(df)
    assert [row.column for row in audit] == FEATURE_COLUMNS[:5]
