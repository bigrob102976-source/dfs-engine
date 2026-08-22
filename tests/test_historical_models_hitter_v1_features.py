"""Milestone 32.3 -- feature allowlist / leakage-guard tests for
historical_models.hitter_v1.features. Both ALWAYS_PREGAME_FEATURE_COLUMNS
and AFTER_LINEUP_FEATURE_COLUMNS are derived directly from
historical_mlb.manifest.hitter_manifest() at import time."""

import pandas as pd
import pytest

from historical_mlb.manifest import HISTORICAL_OUTCOME_ONLY, TARGET, hitter_manifest
from historical_models.hitter_v1.features import (
    AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS,
    AFTER_LINEUP_FEATURE_COLUMNS,
    AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS,
    ALWAYS_PREGAME_FEATURE_COLUMNS,
    CATEGORICAL_FEATURE_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    assert_no_leakage,
    build_feature_audit,
    categorical_columns_for,
    feature_columns_for,
    numeric_columns_for,
)


def test_always_pregame_is_union_of_numeric_and_categorical():
    assert set(ALWAYS_PREGAME_FEATURE_COLUMNS) == set(NUMERIC_FEATURE_COLUMNS) | set(CATEGORICAL_FEATURE_COLUMNS)


def test_after_lineup_is_a_strict_superset_of_always_pregame():
    assert set(ALWAYS_PREGAME_FEATURE_COLUMNS).issubset(set(AFTER_LINEUP_FEATURE_COLUMNS))
    added = set(AFTER_LINEUP_FEATURE_COLUMNS) - set(ALWAYS_PREGAME_FEATURE_COLUMNS)
    assert added == {"opposing_starting_pitcher_hand", "opposing_pitcher_era_season", "opposing_pitcher_k_pct_season", "batting_order_actual"}


def test_every_always_pregame_feature_is_classified_always_pregame_in_manifest():
    manifest_by_name = {f.name: f for f in hitter_manifest()}
    for column in ALWAYS_PREGAME_FEATURE_COLUMNS:
        f = manifest_by_name.get(column)
        assert f is not None, f"{column} is not in hitter_manifest() at all"
        assert f.availability_class == "ALWAYS_PREGAME", f"{column} is {f.availability_class}, not ALWAYS_PREGAME"


def test_after_lineup_additions_are_classified_pregame_after_lineups():
    manifest_by_name = {f.name: f for f in hitter_manifest()}
    additions = set(AFTER_LINEUP_FEATURE_COLUMNS) - set(ALWAYS_PREGAME_FEATURE_COLUMNS)
    for column in additions:
        assert manifest_by_name[column].availability_class == "PREGAME_AFTER_LINEUPS"


def test_target_column_never_in_either_feature_set():
    target_names = {f.name for f in hitter_manifest() if f.availability_class == TARGET}
    assert "actual_dk_points" in target_names
    assert not (target_names & set(ALWAYS_PREGAME_FEATURE_COLUMNS))
    assert not (target_names & set(AFTER_LINEUP_FEATURE_COLUMNS))


def test_no_actual_prefixed_column_in_either_feature_set():
    assert not any(c.startswith("actual_") for c in ALWAYS_PREGAME_FEATURE_COLUMNS)
    assert not any(c.startswith("actual_") for c in AFTER_LINEUP_FEATURE_COLUMNS)


def test_historical_outcome_only_columns_never_in_either_feature_set():
    outcome_only = {f.name for f in hitter_manifest() if f.availability_class == HISTORICAL_OUTCOME_ONLY}
    assert not (outcome_only & set(ALWAYS_PREGAME_FEATURE_COLUMNS))
    assert not (outcome_only & set(AFTER_LINEUP_FEATURE_COLUMNS))


def test_salary_and_vegas_never_in_either_feature_set():
    for forbidden in ("draftkings_salary", "vegas_team_total"):
        assert forbidden not in ALWAYS_PREGAME_FEATURE_COLUMNS
        assert forbidden not in AFTER_LINEUP_FEATURE_COLUMNS


def test_player_identity_never_one_hot_encoded():
    for forbidden in ("player_id", "player_name"):
        assert forbidden not in ALWAYS_PREGAME_FEATURE_COLUMNS
        assert forbidden not in AFTER_LINEUP_FEATURE_COLUMNS


def test_opposing_pitcher_identity_never_a_feature():
    """Explicit instruction: player IDs may be retained for
    joining/evaluation but never as a predictive feature -- this
    applies to the OPPONENT's identity too, not just the hitter's own."""
    assert "opposing_starting_pitcher_id" not in ALWAYS_PREGAME_FEATURE_COLUMNS
    assert "opposing_starting_pitcher_id" not in AFTER_LINEUP_FEATURE_COLUMNS


def test_assert_no_leakage_passes_on_both_real_feature_sets():
    assert_no_leakage(ALWAYS_PREGAME_FEATURE_COLUMNS)
    assert_no_leakage(AFTER_LINEUP_FEATURE_COLUMNS)


@pytest.mark.parametrize("forbidden_column", ["actual_dk_points", "actual_hr", "target_points", "result_flag", "final_score", "postgame_notes"])
def test_assert_no_leakage_rejects_forbidden_columns(forbidden_column):
    with pytest.raises(ValueError):
        assert_no_leakage(ALWAYS_PREGAME_FEATURE_COLUMNS + [forbidden_column])


def test_assert_no_leakage_rejects_identity_columns():
    for forbidden in ("player_id", "player_name", "opposing_starting_pitcher_id"):
        with pytest.raises(ValueError):
            assert_no_leakage(ALWAYS_PREGAME_FEATURE_COLUMNS + [forbidden])


def test_assert_no_leakage_rejects_salary_and_vegas():
    for forbidden in ("draftkings_salary", "vegas_team_total"):
        with pytest.raises(ValueError):
            assert_no_leakage(ALWAYS_PREGAME_FEATURE_COLUMNS + [forbidden])


def test_feature_columns_for_dispatches_correctly():
    assert feature_columns_for("ALWAYS_PREGAME") == ALWAYS_PREGAME_FEATURE_COLUMNS
    assert feature_columns_for("AFTER_LINEUP") == AFTER_LINEUP_FEATURE_COLUMNS
    assert numeric_columns_for("AFTER_LINEUP") == AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS
    assert categorical_columns_for("AFTER_LINEUP") == AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS
    with pytest.raises(ValueError):
        feature_columns_for("NOT_A_REAL_CLASS")


def test_build_feature_audit_marks_target_and_included_columns_correctly():
    df = pd.DataFrame({
        "actual_dk_points": [10.0, 12.0],
        ALWAYS_PREGAME_FEATURE_COLUMNS[0]: [1.0, 2.0],
        "draftkings_salary": [None, None],
        "opposing_starting_pitcher_id": ["123", "456"],
        "batting_order_actual": [3, 5],
        "lineup_availability": ["confirmed", "confirmed"],
        "not_a_real_column_xyz": [1, 2],
    })
    audit = build_feature_audit(df)
    by_column = {row.column: row for row in audit}

    assert by_column["actual_dk_points"].included_always_pregame is False
    assert by_column["actual_dk_points"].included_after_lineup is False

    assert by_column[ALWAYS_PREGAME_FEATURE_COLUMNS[0]].included_always_pregame is True
    assert by_column[ALWAYS_PREGAME_FEATURE_COLUMNS[0]].included_after_lineup is True

    assert by_column["draftkings_salary"].included_always_pregame is False

    assert by_column["opposing_starting_pitcher_id"].included_always_pregame is False
    assert by_column["opposing_starting_pitcher_id"].included_after_lineup is False
    assert "identity" in by_column["opposing_starting_pitcher_id"].reason.lower()

    assert by_column["batting_order_actual"].included_always_pregame is False
    assert by_column["batting_order_actual"].included_after_lineup is True

    assert by_column["lineup_availability"].included_always_pregame is False
    assert "constant" in by_column["lineup_availability"].reason.lower()

    assert by_column["not_a_real_column_xyz"].included_always_pregame is False
    assert "not in the hitter feature manifest" in by_column["not_a_real_column_xyz"].reason
