from datetime import datetime, timezone

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


# 2026-09-01 disk incident: local_raw_archive_enabled() / prune_local_raw_archive()


def test_local_raw_archive_enabled_falls_back_to_default_when_unset(monkeypatch):
    monkeypatch.delenv(persistence.LOCAL_RAW_ARCHIVE_ENV_VAR, raising=False)
    assert persistence.local_raw_archive_enabled(default=False) is False
    assert persistence.local_raw_archive_enabled(default=True) is True


def test_local_raw_archive_enabled_explicit_true_wins_over_default_false(monkeypatch):
    monkeypatch.setenv(persistence.LOCAL_RAW_ARCHIVE_ENV_VAR, "true")
    assert persistence.local_raw_archive_enabled(default=False) is True


def test_local_raw_archive_enabled_explicit_false_wins_over_default_true(monkeypatch):
    monkeypatch.setenv(persistence.LOCAL_RAW_ARCHIVE_ENV_VAR, "false")
    assert persistence.local_raw_archive_enabled(default=True) is False


def test_local_raw_archive_enabled_accepts_common_truthy_falsy_variants(monkeypatch):
    for value in ("true", "True", "1", "yes", "YES"):
        monkeypatch.setenv(persistence.LOCAL_RAW_ARCHIVE_ENV_VAR, value)
        assert persistence.local_raw_archive_enabled(default=False) is True
    for value in ("false", "False", "0", "no", "NO"):
        monkeypatch.setenv(persistence.LOCAL_RAW_ARCHIVE_ENV_VAR, value)
        assert persistence.local_raw_archive_enabled(default=True) is False


def test_prune_removes_only_directories_older_than_retention_window(tmp_path):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    persistence.save_raw("sports", "old", {"a": 1}, archive_root=tmp_path, date="2026-08-20")
    persistence.save_raw("sports", "recent", {"a": 1}, archive_root=tmp_path, date="2026-08-31")

    removed = persistence.prune_local_raw_archive(max_age_days=3, archive_root=tmp_path, now=now)

    removed_names = {p.name for p in removed}
    assert "2026-08-20" in removed_names
    assert "2026-08-31" not in removed_names
    assert not (tmp_path / "raw" / "2026-08-20").exists()
    assert (tmp_path / "raw" / "2026-08-31").exists()


def test_prune_also_covers_normalized_directory(tmp_path):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    persistence.save_normalized("x", {"a": 1}, archive_root=tmp_path, date="2026-08-01")
    persistence.prune_local_raw_archive(max_age_days=3, archive_root=tmp_path, now=now)
    assert not (tmp_path / "normalized" / "2026-08-01").exists()


def test_prune_ignores_non_date_named_entries(tmp_path):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    stray = tmp_path / "raw" / "not-a-date"
    stray.mkdir(parents=True)
    (stray / "file.txt").write_text("x")
    persistence.prune_local_raw_archive(max_age_days=3, archive_root=tmp_path, now=now)
    assert stray.exists()  # never touched -- not a YYYY-MM-DD directory


def test_prune_never_escapes_archive_root_via_symlink(tmp_path):
    # A directory named like a valid retention-eligible date, but that is
    # actually a symlink pointing OUTSIDE archive_root, must be refused,
    # not deleted -- proves cleanup/pruning cannot escape the intended
    # directory.
    outside = tmp_path.parent / "outside_target"
    outside.mkdir()
    (outside / "do_not_delete.txt").write_text("precious")

    archive_root = tmp_path / "archive"
    (archive_root / "raw").mkdir(parents=True)
    link_path = archive_root / "raw" / "2020-01-01"
    try:
        link_path.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")

    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    persistence.prune_local_raw_archive(max_age_days=3, archive_root=archive_root, now=now)

    assert outside.exists()
    assert (outside / "do_not_delete.txt").exists()


def test_prune_returns_empty_list_when_nothing_is_old_enough(tmp_path):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    persistence.save_raw("sports", "recent", {"a": 1}, archive_root=tmp_path, date="2026-08-31")
    removed = persistence.prune_local_raw_archive(max_age_days=3, archive_root=tmp_path, now=now)
    assert removed == []
