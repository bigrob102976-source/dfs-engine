import json

import pytest

from projection_engine.persistence import (
    list_ai_projection_snapshots,
    load_latest_ai_projection_snapshot,
    load_latest_dfs_pool,
    load_latest_ownership,
    save_ai_projection_snapshot,
)


def _document(date="2026-08-14", generated_at="2026-08-14T18:00:00+00:00"):
    return {"slate_date": date, "generated_at": generated_at, "players": []}


def test_save_ai_projection_snapshot_creates_expected_path(tmp_path):
    path = save_ai_projection_snapshot(_document(), output_root=tmp_path)
    assert path.name == "ai_projection_20260814T180000.json"
    assert path.exists()


def test_save_ai_projection_snapshot_never_overwrites(tmp_path):
    save_ai_projection_snapshot(_document(), output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_ai_projection_snapshot(_document(), output_root=tmp_path)


def test_load_latest_ai_projection_snapshot_picks_newest(tmp_path):
    save_ai_projection_snapshot(_document(generated_at="2026-08-14T18:00:00+00:00"), output_root=tmp_path)
    save_ai_projection_snapshot(_document(generated_at="2026-08-14T19:00:00+00:00"), output_root=tmp_path)
    latest = load_latest_ai_projection_snapshot("2026-08-14", output_root=tmp_path)
    assert latest["generated_at"] == "2026-08-14T19:00:00+00:00"


def test_load_latest_ai_projection_snapshot_none_when_missing(tmp_path):
    assert load_latest_ai_projection_snapshot("2026-08-14", output_root=tmp_path) is None


def test_list_ai_projection_snapshots_empty_when_no_folder(tmp_path):
    assert list_ai_projection_snapshots("2026-08-14", output_root=tmp_path) == []


# ----------------------------------------------------------------------------
# load_latest_ownership -- degrades to None instead of raising
# ----------------------------------------------------------------------------


def test_load_latest_ownership_none_when_missing(monkeypatch):
    import projection_engine.persistence as pe_persistence

    def _raise(slate_date):
        raise FileNotFoundError("no snapshot for this test")

    # Patches the name AS BOUND IN projection_engine.persistence's own
    # namespace (from the `from ownership.persistence import ...` at the
    # top of this module) -- ownership.persistence's default `output_root`
    # argument is resolved at import time, so patching the module-level
    # constant there would not affect this already-bound default.
    monkeypatch.setattr(pe_persistence, "load_latest_ownership_snapshot", _raise)
    assert load_latest_ownership("2026-08-14") is None


# ----------------------------------------------------------------------------
# load_latest_dfs_pool
# ----------------------------------------------------------------------------


def test_load_latest_dfs_pool_none_when_missing(tmp_path):
    assert load_latest_dfs_pool("2026-08-14", output_root=tmp_path) is None


def test_load_latest_dfs_pool_picks_newest(tmp_path):
    folder = tmp_path / "2026-08-14"
    folder.mkdir(parents=True)
    (folder / "dk_player_pool_20260814T180000.json").write_text(json.dumps({"players": [], "tag": "first"}), encoding="utf-8")
    (folder / "dk_player_pool_20260814T190000.json").write_text(json.dumps({"players": [], "tag": "second"}), encoding="utf-8")
    pool = load_latest_dfs_pool("2026-08-14", output_root=tmp_path)
    assert pool["tag"] == "second"
