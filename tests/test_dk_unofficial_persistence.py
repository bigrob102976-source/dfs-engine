import pytest

from draftkings_unofficial import persistence


def test_save_and_load_raw_roundtrip(tmp_path):
    path = persistence.save_raw("sports", "sports", {"sports": [1, 2]}, archive_root=tmp_path, date="2026-08-20")
    assert path.exists()
    loaded = persistence.load_latest_raw("sports", "sports", "2026-08-20", archive_root=tmp_path)
    assert loaded == {"sports": [1, 2]}


def test_save_raw_rejects_unknown_category(tmp_path):
    with pytest.raises(ValueError):
        persistence.save_raw("bogus_category", "x", {}, archive_root=tmp_path, date="2026-08-20")


def test_save_raw_refuses_to_overwrite_same_second(tmp_path, monkeypatch):
    import draftkings_unofficial.persistence as p

    monkeypatch.setattr(p, "_timestamp_tag", lambda now=None: "FIXED")
    p.save_raw("sports", "sports", {"a": 1}, archive_root=tmp_path, date="2026-08-20")
    with pytest.raises(FileExistsError):
        p.save_raw("sports", "sports", {"a": 2}, archive_root=tmp_path, date="2026-08-20")


def test_two_different_timestamps_both_saved(tmp_path):
    p1 = persistence.save_raw("draftables", "152389", {"n": 1}, archive_root=tmp_path, date="2026-08-20")
    import time

    time.sleep(1.01)
    p2 = persistence.save_raw("draftables", "152389", {"n": 2}, archive_root=tmp_path, date="2026-08-20")
    assert p1 != p2
    assert p1.exists() and p2.exists()


def test_load_latest_raw_returns_none_when_nothing_saved(tmp_path):
    assert persistence.load_latest_raw("sports", "sports", "2026-08-20", archive_root=tmp_path) is None


def test_load_latest_raw_returns_most_recent_by_filename(tmp_path):
    import time

    persistence.save_raw("contests", "MLB", {"v": "old"}, archive_root=tmp_path, date="2026-08-20")
    time.sleep(1.01)
    persistence.save_raw("contests", "MLB", {"v": "new"}, archive_root=tmp_path, date="2026-08-20")
    loaded = persistence.load_latest_raw("contests", "MLB", "2026-08-20", archive_root=tmp_path)
    assert loaded == {"v": "new"}


def test_list_raw_snapshots_empty_when_nothing_saved(tmp_path):
    assert persistence.list_raw_snapshots("sports", "2026-08-20", archive_root=tmp_path) == []


def test_save_and_list_normalized(tmp_path):
    persistence.save_normalized("mlb_slate_152389", {"x": 1}, archive_root=tmp_path, date="2026-08-20")
    snapshots = persistence.list_normalized_snapshots("2026-08-20", archive_root=tmp_path)
    assert len(snapshots) == 1


def test_saved_raw_file_never_contains_api_key_field(tmp_path):
    # This provider has no API key at all -- confirms the archive never
    # accidentally acquires one via some future copy-paste of another
    # provider's persistence pattern.
    path = persistence.save_raw("sports", "sports", {"sports": []}, archive_root=tmp_path, date="2026-08-20")
    content = path.read_text(encoding="utf-8")
    assert "api_key" not in content.lower() and "apikey" not in content.lower()
