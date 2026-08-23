import json

import pytest

from bluecollar.persistence import list_bluecollar_snapshots, load_latest_bluecollar_snapshot, save_bluecollar_snapshot


def _document(retrieved_at="2026-08-23T18:00:00+00:00", dk_slate_id="dkunofficial-152551"):
    return {
        "slate_date": "2026-08-23", "dk_slate_id": dk_slate_id, "bluecollar_slate_id": "bluecollar-main",
        "bluecollar_slate_name": "1:35PM ET Main 8 Games", "bluecollar_updated": "12:36:44 ET",
        "retrieved_at": retrieved_at, "slate_match_status": "matched", "slate_match_reason": None,
        "player_count": 746, "matched_count": 15, "usable_projection_count": 159, "players": [],
    }


def test_save_and_no_overwrite(tmp_path):
    doc = _document()
    path = save_bluecollar_snapshot(doc, "2026-08-23", "dkunofficial-152551", "20260823T180000", output_root=tmp_path)
    assert path.exists()
    assert path.name == "bluecollar_projection_20260823T180000.json"

    with pytest.raises(FileExistsError):
        save_bluecollar_snapshot(doc, "2026-08-23", "dkunofficial-152551", "20260823T180000", output_root=tmp_path)


def test_save_path_is_always_slate_scoped(tmp_path):
    doc = _document()
    path = save_bluecollar_snapshot(doc, "2026-08-23", "dkunofficial-152551", "20260823T180000", output_root=tmp_path)
    assert path == tmp_path / "2026-08-23" / "dkunofficial-152551" / "bluecollar_projection_20260823T180000.json"


def test_list_and_load_latest_snapshot(tmp_path):
    doc1 = _document(retrieved_at="2026-08-23T14:00:00+00:00")
    doc2 = _document(retrieved_at="2026-08-23T20:00:00+00:00")
    save_bluecollar_snapshot(doc1, "2026-08-23", "dkunofficial-152551", "20260823T140000", output_root=tmp_path)
    save_bluecollar_snapshot(doc2, "2026-08-23", "dkunofficial-152551", "20260823T200000", output_root=tmp_path)

    snapshots = list_bluecollar_snapshots("2026-08-23", "dkunofficial-152551", output_root=tmp_path)
    assert len(snapshots) == 2

    latest = load_latest_bluecollar_snapshot("2026-08-23", "dkunofficial-152551", output_root=tmp_path)
    assert latest["retrieved_at"] == "2026-08-23T20:00:00+00:00"


def test_load_latest_returns_none_when_none_exist_never_raises(tmp_path):
    # Unlike ownership (date-only fallback exists), BlueCollar is ALWAYS
    # slate-scoped -- a genuinely missing snapshot must be a clean None
    # so the dashboard can show "BLUECOLLAR NOT UPDATED" honestly rather
    # than crashing.
    assert load_latest_bluecollar_snapshot("2026-08-23", "dkunofficial-152551", output_root=tmp_path) is None


def test_two_dk_slates_sharing_a_date_never_collide_or_leak(tmp_path):
    main_doc = _document(dk_slate_id="dkunofficial-152551")
    turbo_doc = _document(dk_slate_id="dkunofficial-152556")

    save_bluecollar_snapshot(main_doc, "2026-08-23", "dkunofficial-152551", "20260823T180000", output_root=tmp_path)
    save_bluecollar_snapshot(turbo_doc, "2026-08-23", "dkunofficial-152556", "20260823T180500", output_root=tmp_path)

    latest_main = load_latest_bluecollar_snapshot("2026-08-23", "dkunofficial-152551", output_root=tmp_path)
    latest_turbo = load_latest_bluecollar_snapshot("2026-08-23", "dkunofficial-152556", output_root=tmp_path)

    assert latest_main["dk_slate_id"] == "dkunofficial-152551"
    assert latest_turbo["dk_slate_id"] == "dkunofficial-152556"


def test_saved_json_round_trips(tmp_path):
    doc = _document()
    path = save_bluecollar_snapshot(doc, "2026-08-23", "dkunofficial-152551", "20260823T180000", output_root=tmp_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["player_count"] == doc["player_count"]
    assert loaded["dk_slate_id"] == doc["dk_slate_id"]


def test_never_stores_the_api_key():
    doc = _document()
    assert "api_key" not in json.dumps(doc).lower()
    assert "authorization" not in json.dumps(doc).lower()
