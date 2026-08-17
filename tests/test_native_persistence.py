import pytest

from native_projections.models import NativeProjectionDocument
from native_projections.persistence import (
    list_native_projection_snapshots,
    load_latest_native_projection_snapshot,
    load_native_projection_snapshot,
    save_native_projection_document,
)
from native_projections.version import NATIVE_PROJECTION_MODEL_VERSION


def make_document(**overrides):
    defaults = dict(
        slate_date="2026-08-17",
        generated_at="2026-08-17T16:55:00+00:00",
        model_version=NATIVE_PROJECTION_MODEL_VERSION,
        pitcher_snapshot_path=None,
        batter_snapshot_path=None,
        environment_snapshot_path=None,
        player_count=0,
        players=[],
    )
    defaults.update(overrides)
    return NativeProjectionDocument(**defaults)


def test_save_creates_expected_file(tmp_path):
    doc = make_document()
    path = save_native_projection_document(doc, output_root=tmp_path)
    assert path.exists()
    assert path.parent.name == "2026-08-17"
    assert path.name.startswith("native_projection_")
    assert path.name.endswith(".json")


def test_save_refuses_to_overwrite_existing_snapshot(tmp_path):
    doc = make_document()
    save_native_projection_document(doc, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_native_projection_document(doc, output_root=tmp_path)


def test_list_snapshots_empty_when_no_folder(tmp_path):
    assert list_native_projection_snapshots("2026-08-17", output_root=tmp_path) == []


def test_list_snapshots_returns_saved_files(tmp_path):
    doc1 = make_document(generated_at="2026-08-17T10:00:00+00:00")
    doc2 = make_document(generated_at="2026-08-17T14:00:00+00:00")
    save_native_projection_document(doc1, output_root=tmp_path)
    save_native_projection_document(doc2, output_root=tmp_path)
    snapshots = list_native_projection_snapshots("2026-08-17", output_root=tmp_path)
    assert len(snapshots) == 2


def test_load_latest_returns_most_recent(tmp_path):
    doc1 = make_document(generated_at="2026-08-17T10:00:00+00:00", player_count=1)
    doc2 = make_document(generated_at="2026-08-17T14:00:00+00:00", player_count=2)
    save_native_projection_document(doc1, output_root=tmp_path)
    save_native_projection_document(doc2, output_root=tmp_path)
    latest = load_latest_native_projection_snapshot("2026-08-17", output_root=tmp_path)
    assert latest["player_count"] == 2


def test_load_latest_raises_when_none_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_latest_native_projection_snapshot("2026-08-17", output_root=tmp_path)


def test_round_trip_content_matches(tmp_path):
    doc = make_document(player_count=0)
    path = save_native_projection_document(doc, output_root=tmp_path)
    loaded = load_native_projection_snapshot(path)
    assert loaded["slate_date"] == "2026-08-17"
    assert loaded["model_version"] == NATIVE_PROJECTION_MODEL_VERSION
