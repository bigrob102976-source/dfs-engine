import json

import pytest

from fantasypros.models import FantasyProsPlayerProjection, FantasyProsSnapshot
from fantasypros.persistence import load_latest_snapshot, list_snapshots, save_snapshot


def _snapshot(date="2026-08-19", retrieved_at="2026-08-19T18:00:00+00:00"):
    return FantasyProsSnapshot(
        slate_date=date, retrieved_at=retrieved_at, hitter_count=1, pitcher_count=1,
        hitters_matched=1, pitchers_matched=1, public_api_limited=True, api_tier="free",
        players=[FantasyProsPlayerProjection(fantasypros_id="1", name="Test Player", team="LAD", player_type="hitter", dk_points=8.5)],
    )


def test_save_and_load_roundtrip(tmp_path):
    snap = _snapshot()
    path = save_snapshot(snap, output_root=tmp_path)
    assert path.exists()

    loaded = load_latest_snapshot("2026-08-19", output_root=tmp_path)
    assert loaded["slate_date"] == "2026-08-19"
    assert loaded["hitter_count"] == 1
    assert loaded["players"][0]["name"] == "Test Player"
    assert loaded["players"][0]["dk_points"] == 8.5


def test_refuses_to_overwrite_same_second(tmp_path):
    snap = _snapshot()
    save_snapshot(snap, output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_snapshot(snap, output_root=tmp_path)  # identical retrieved_at -> identical filename


def test_two_snapshots_different_timestamps_both_saved(tmp_path):
    save_snapshot(_snapshot(retrieved_at="2026-08-19T18:00:00+00:00"), output_root=tmp_path)
    save_snapshot(_snapshot(retrieved_at="2026-08-19T19:00:00+00:00"), output_root=tmp_path)
    assert len(list_snapshots("2026-08-19", output_root=tmp_path)) == 2


def test_load_latest_returns_the_most_recent(tmp_path):
    save_snapshot(_snapshot(retrieved_at="2026-08-19T18:00:00+00:00"), output_root=tmp_path)
    save_snapshot(_snapshot(retrieved_at="2026-08-19T19:30:00+00:00"), output_root=tmp_path)
    loaded = load_latest_snapshot("2026-08-19", output_root=tmp_path)
    assert loaded["retrieved_at"] == "2026-08-19T19:30:00+00:00"


def test_load_latest_returns_none_when_no_snapshot_exists(tmp_path):
    assert load_latest_snapshot("2026-08-19", output_root=tmp_path) is None


def test_saved_snapshot_never_contains_an_api_key_field(tmp_path):
    path = save_snapshot(_snapshot(), output_root=tmp_path)
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    assert "api_key" not in raw.lower().replace(" ", "")
    assert "fantasypros_api_key" not in json.dumps(doc).lower()
