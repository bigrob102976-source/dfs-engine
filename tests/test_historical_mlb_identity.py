"""Milestone 32.0 -- historical_mlb/identity.py. No network calls."""

import pytest

from historical_mlb.identity import (
    attach_external_source_id,
    build_crosswalk_index,
    crosswalk_row_from_mlbam,
    merge_chadwick_register_row,
)


def test_crosswalk_row_from_mlbam_basic():
    row = crosswalk_row_from_mlbam(592450, "Aaron Judge", "NYY")
    assert row.canonical_player_id == "592450"
    assert row.mlbam_id == "592450"
    assert row.statcast_id == "592450"  # Statcast IDs ARE mlbam ids
    assert row.normalized_name is not None
    assert row.match_method == "mlbam_direct"
    assert row.match_confidence == 1.0


def test_merge_chadwick_register_row_populates_other_ids():
    row = crosswalk_row_from_mlbam(592450, "Aaron Judge", "NYY")
    register_row = {"key_mlbam": 592450, "key_bbref": "judgeaa01", "key_fangraphs": 15640, "key_retro": "judga001"}
    merged = merge_chadwick_register_row(row, register_row)
    assert merged.bbref_id == "judgeaa01"
    assert merged.fangraphs_id == "15640"
    assert merged.retrosheet_id == "judga001"
    assert merged.match_method == "chadwick_register"


def test_merge_chadwick_register_row_ignores_mismatched_mlbam_id():
    row = crosswalk_row_from_mlbam(592450, "Aaron Judge", "NYY")
    register_row = {"key_mlbam": 999999, "key_bbref": "someoneelse01"}
    merged = merge_chadwick_register_row(row, register_row)
    assert merged.bbref_id is None  # not overwritten -- wrong player


def test_merge_chadwick_register_row_never_overwrites_existing_field():
    row = crosswalk_row_from_mlbam(592450, "Aaron Judge", "NYY")
    row.bbref_id = "manually-set"
    merged = merge_chadwick_register_row(row, {"key_mlbam": 592450, "key_bbref": "judgeaa01"})
    assert merged.bbref_id == "manually-set"


def test_attach_external_source_id_draftkings():
    row = crosswalk_row_from_mlbam(592450, "Aaron Judge", "NYY")
    attach_external_source_id(row, "draftkings_id", "dk-12345", "Aaron Judge", confidence=0.95)
    assert row.draftkings_id == "dk-12345"
    assert row.match_confidence == 0.95
    assert row.match_method == "name_fallback"


def test_attach_external_source_id_rejects_unknown_source():
    row = crosswalk_row_from_mlbam(592450, "Aaron Judge", "NYY")
    with pytest.raises(ValueError):
        attach_external_source_id(row, "some_other_source", "x", "x", 1.0)


def test_build_crosswalk_index_ok():
    rows = [crosswalk_row_from_mlbam(1, "A", "NYY"), crosswalk_row_from_mlbam(2, "B", "BOS")]
    index = build_crosswalk_index(rows)
    assert set(index) == {"1", "2"}


def test_build_crosswalk_index_raises_on_duplicate_canonical_id():
    rows = [crosswalk_row_from_mlbam(1, "A", "NYY"), crosswalk_row_from_mlbam(1, "A-dup", "NYY")]
    with pytest.raises(ValueError):
        build_crosswalk_index(rows)
