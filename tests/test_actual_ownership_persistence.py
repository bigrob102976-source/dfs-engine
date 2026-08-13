import json

import pytest

from evaluation.actual_ownership_models import ActualOwnershipRecord, ContestMetadata
from evaluation.actual_ownership_persistence import build_actual_ownership_document, save_actual_ownership_document


def _contest(contest_id="555"):
    return ContestMetadata(
        contest_id=contest_id, contest_name=None, contest_type=None, entries=2, max_entries=None,
        results_filename="f.csv", source_file_hash="abc123", retrieved_at_utc="2026-08-11T18:00:00+00:00",
    )


def _records():
    return [
        ActualOwnershipRecord(
            dk_player_id="d1", mlb_player_id="m1", name="Player One", team="TOR", player_type="pitcher",
            actual_ownership=63.4, contest_id="555", contest_name=None, contest_size=2, source_file="f.csv",
            match_status="matched", match_confidence="exact_dk_id",
        ),
        ActualOwnershipRecord(
            dk_player_id=None, mlb_player_id=None, name="Unknown Player", team=None, player_type=None,
            actual_ownership=5.0, contest_id="555", contest_name=None, contest_size=2, source_file="f.csv",
            match_status="unmatched", match_confidence=None,
        ),
    ]


def test_document_includes_contest_and_match_counts():
    doc = build_actual_ownership_document("2026-08-11", _contest(), "direct_ownership_table", [], _records())
    assert doc["contest"]["contest_id"] == "555"
    assert doc["record_count"] == 2
    assert doc["matched_count"] == 1
    assert doc["unmatched_count"] == 1
    assert doc["match_rate"] == 0.5


def test_save_and_no_overwrite(tmp_path):
    doc = build_actual_ownership_document("2026-08-11", _contest(), "direct_ownership_table", [], _records())
    path = save_actual_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    assert path.exists()
    assert path.name == "contest_555_20260811T180000.json"

    with pytest.raises(FileExistsError):
        save_actual_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)


def test_missing_contest_id_falls_back_to_unknown_in_filename(tmp_path):
    doc = build_actual_ownership_document("2026-08-11", _contest(contest_id=None), "derived_from_lineups", [], _records())
    path = save_actual_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    assert "unknown" in path.name


def test_saved_document_round_trips(tmp_path):
    doc = build_actual_ownership_document("2026-08-11", _contest(), "direct_ownership_table", ["a warning"], _records())
    path = save_actual_ownership_document(doc, "2026-08-11", "20260811T180000", output_root=tmp_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["import_warnings"] == ["a warning"]
    assert len(loaded["records"]) == 2


def test_actual_ownership_never_saved_under_other_data_roots():
    from evaluation.actual_ownership_persistence import DEFAULT_ACTUAL_OWNERSHIP_ROOT
    forbidden = {"ownership_predictions", "predictions", "dfs_input"}
    assert DEFAULT_ACTUAL_OWNERSHIP_ROOT.name not in forbidden
    assert DEFAULT_ACTUAL_OWNERSHIP_ROOT.name == "actual_ownership"
