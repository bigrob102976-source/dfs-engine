import csv
import json

import pytest

from evaluation.ownership_evaluation_persistence import build_evaluation_document, save_evaluation_csv, save_evaluation_json
from evaluation.ownership_evaluator import evaluate_ownership
from tests._ownership_evaluation_fixtures import sample_actual_document, sample_snapshot


def _document(generated_at="2026-08-11T18:00:00+00:00"):
    report = evaluate_ownership(sample_snapshot(), sample_actual_document())
    return build_evaluation_document(report.to_dict(), generated_at)


def test_document_has_timezone_provenance():
    doc = _document()
    assert doc["generated_at_utc"] == "2026-08-11T18:00:00+00:00"
    assert doc["timezone"] == "America/Chicago"
    assert "generated_at_local" in doc


def test_json_save_and_no_overwrite(tmp_path):
    doc = _document()
    path = save_evaluation_json(doc, "2026-08-11", "999", "20260811T180000", output_root=tmp_path)
    assert path.exists()
    assert path.name == "contest_999_ownership_eval_20260811T180000.json"
    with pytest.raises(FileExistsError):
        save_evaluation_json(doc, "2026-08-11", "999", "20260811T180000", output_root=tmp_path)


def test_csv_save_and_columns(tmp_path):
    doc = _document()
    path = save_evaluation_csv(doc, "2026-08-11", "999", "20260811T180000", output_root=tmp_path)
    assert path.exists()
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == [
        "date", "contest_id", "dk_player_id", "name", "team", "position", "salary",
        "projected_ownership", "actual_ownership", "error", "absolute_error",
        "projected_rank", "actual_rank", "ownership_model_version",
    ]
    assert len(rows) == 1 + 8  # header + 8 matched players


def test_csv_only_includes_matched_players(tmp_path):
    doc = _document()
    doc["records"].append({
        "dk_player_id": None, "matched": False, "name": "Ghost", "team": None, "dk_positions": [],
        "salary": None, "projected_ownership": None, "actual_ownership": None, "error": None,
        "abs_error": None, "projected_rank": None, "actual_rank": None,
    })
    path = save_evaluation_csv(doc, "2026-08-11", "999", "20260811T190000", output_root=tmp_path)
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    names = {row[3] for row in rows[1:]}
    assert "Ghost" not in names


def test_multiple_contests_never_merged(tmp_path):
    doc = _document()
    path_a = save_evaluation_json(doc, "2026-08-11", "111", "20260811T180000", output_root=tmp_path)
    path_b = save_evaluation_json(doc, "2026-08-11", "222", "20260811T180000", output_root=tmp_path)
    assert path_a != path_b
    assert "contest_111" in path_a.name
    assert "contest_222" in path_b.name
    assert path_a.exists() and path_b.exists()


def test_saved_json_round_trips():
    import tempfile
    from pathlib import Path
    doc = _document()
    with tempfile.TemporaryDirectory() as tmp:
        path = save_evaluation_json(doc, "2026-08-11", "999", "20260811T180000", output_root=Path(tmp))
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["matched_count"] == doc["matched_count"]
