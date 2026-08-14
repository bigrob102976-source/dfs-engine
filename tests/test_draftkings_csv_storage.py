import pytest

from dfs.providers.draftkings_csv_storage import delete_upload, list_uploads, save_upload

CSV_BYTES = b"Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\nP,Ace (1),Ace,1,P,9000,TOR@BOS,TOR,20\n"


def test_save_upload_writes_csv_and_meta(tmp_path):
    upload = save_upload(CSV_BYTES, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    assert upload.slate_label == "Main"
    assert upload.original_filename == "DKSalaries.csv"
    from pathlib import Path
    assert Path(upload.path).read_bytes() == CSV_BYTES
    assert Path(upload.meta_path).exists()


def test_list_uploads_returns_empty_for_unknown_date(tmp_path):
    assert list_uploads("2026-08-14", output_root=tmp_path) == []


def test_list_uploads_returns_saved_uploads(tmp_path):
    save_upload(CSV_BYTES, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    save_upload(CSV_BYTES, "2026-08-14", "Turbo", "DKSalariesTurbo.csv", output_root=tmp_path)
    uploads = list_uploads("2026-08-14", output_root=tmp_path)
    labels = {u.slate_label for u in uploads}
    assert labels == {"Main", "Turbo"}


def test_list_uploads_skips_corrupt_meta_sidecar(tmp_path):
    upload = save_upload(CSV_BYTES, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    from pathlib import Path
    Path(upload.meta_path).write_text("not valid json", encoding="utf-8")
    assert list_uploads("2026-08-14", output_root=tmp_path) == []


def test_save_upload_never_overwrites_same_label(tmp_path):
    first = save_upload(CSV_BYTES, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path, uploaded_at="2026-08-14T18:00:00Z")
    second = save_upload(CSV_BYTES, "2026-08-14", "Main", "DKSalaries2.csv", output_root=tmp_path, uploaded_at="2026-08-14T18:00:01Z")
    assert first.path != second.path
    uploads = list_uploads("2026-08-14", output_root=tmp_path)
    assert len(uploads) == 2


def test_delete_upload_removes_csv_and_meta(tmp_path):
    upload = save_upload(CSV_BYTES, "2026-08-14", "Main", "DKSalaries.csv", output_root=tmp_path)
    delete_upload(upload.path, output_root=tmp_path)
    from pathlib import Path
    assert not Path(upload.path).exists()
    assert not Path(upload.meta_path).exists()
    assert list_uploads("2026-08-14", output_root=tmp_path) == []


def test_delete_upload_refuses_path_outside_root(tmp_path):
    outside = tmp_path / "elsewhere.csv"
    outside.write_bytes(CSV_BYTES)
    with pytest.raises(ValueError):
        delete_upload(str(outside), output_root=tmp_path)


def test_delete_upload_refuses_path_not_in_uploaded_subdir(tmp_path):
    (tmp_path / "2026-08-14").mkdir(parents=True)
    rogue = tmp_path / "2026-08-14" / "not_an_upload.csv"
    rogue.write_bytes(CSV_BYTES)
    with pytest.raises(ValueError):
        delete_upload(str(rogue), output_root=tmp_path)
