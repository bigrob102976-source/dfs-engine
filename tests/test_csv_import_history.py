import pytest

from external_projections.csv_import.history import delete_import, list_imports, reactivate_import
from external_projections.persistence import save_baseline_snapshot


def _csv_doc(date="2026-08-11", provider="bluecollar", retrieved_at="2026-08-11T18:00:00+00:00", player_count=2):
    return {
        "slate_date": date, "provider": provider, "provider_name": "BlueCollar DFS",
        "retrieved_at": retrieved_at, "player_count": player_count, "players": [],
        "source": "csv_import", "original_filename": "mock.csv",
        "validation_summary": {"matched": 1, "unmatched": 1, "ambiguous": 0},
    }


def _non_import_doc(date="2026-08-11", retrieved_at="2026-08-11T20:00:00+00:00"):
    return {"slate_date": date, "provider": "mock_external_projections", "provider_name": "MOCK EXTERNAL PROJECTIONS",
            "retrieved_at": retrieved_at, "player_count": 0, "players": []}


def test_list_imports_only_includes_csv_imports(tmp_path):
    save_baseline_snapshot(_csv_doc(), output_root=tmp_path)
    save_baseline_snapshot(_non_import_doc(), output_root=tmp_path)
    imports = list_imports("2026-08-11", output_root=tmp_path)
    assert len(imports) == 1
    assert imports[0]["provider"] == "bluecollar"


def test_list_imports_newest_first(tmp_path):
    save_baseline_snapshot(_csv_doc(provider="bluecollar", retrieved_at="2026-08-11T18:00:00+00:00"), output_root=tmp_path)
    save_baseline_snapshot(_csv_doc(provider="custom_csv", retrieved_at="2026-08-11T19:00:00+00:00"), output_root=tmp_path)
    imports = list_imports("2026-08-11", output_root=tmp_path)
    assert [i["provider"] for i in imports] == ["custom_csv", "bluecollar"]


def test_is_active_reflects_the_actual_latest_snapshot(tmp_path):
    save_baseline_snapshot(_csv_doc(provider="bluecollar", retrieved_at="2026-08-11T18:00:00+00:00"), output_root=tmp_path)
    save_baseline_snapshot(_csv_doc(provider="fantasycruncher", retrieved_at="2026-08-11T19:00:00+00:00"), output_root=tmp_path)
    imports = list_imports("2026-08-11", output_root=tmp_path)
    by_provider = {i["provider"]: i for i in imports}
    assert by_provider["fantasycruncher"]["is_active"] is True
    assert by_provider["bluecollar"]["is_active"] is False


def test_list_imports_empty_when_no_snapshots(tmp_path):
    assert list_imports("2026-08-11", output_root=tmp_path) == []


def test_reactivate_writes_a_new_newer_copy(tmp_path):
    path = save_baseline_snapshot(_csv_doc(retrieved_at="2026-08-11T18:00:00+00:00"), output_root=tmp_path)
    new_path = reactivate_import(str(path), output_root=tmp_path)
    assert new_path != str(path)
    imports = list_imports("2026-08-11", output_root=tmp_path)
    assert len(imports) == 2
    assert any(i["is_active"] for i in imports if i["path"] == new_path)


def test_reactivate_refuses_a_non_csv_import_snapshot(tmp_path):
    path = save_baseline_snapshot(_non_import_doc(), output_root=tmp_path)
    with pytest.raises(ValueError):
        reactivate_import(str(path), output_root=tmp_path)


def test_delete_removes_the_file(tmp_path):
    path = save_baseline_snapshot(_csv_doc(), output_root=tmp_path)
    assert path.exists()
    delete_import(str(path), output_root=tmp_path)
    assert not path.exists()


def test_delete_refuses_a_non_csv_import_snapshot(tmp_path):
    path = save_baseline_snapshot(_non_import_doc(), output_root=tmp_path)
    with pytest.raises(ValueError):
        delete_import(str(path), output_root=tmp_path)
    assert path.exists()


def test_delete_refuses_a_path_outside_the_snapshot_root(tmp_path):
    outside = tmp_path.parent / "outside_provider_evil_20260101T000000.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        with pytest.raises(ValueError):
            delete_import(str(outside), output_root=tmp_path)
    finally:
        outside.unlink()
