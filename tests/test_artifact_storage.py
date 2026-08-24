"""Milestone 30: tests for research/artifact_storage.py -- the Python
storage abstraction (LocalArtifactStorage / S3ArtifactStorage) and its
integration into research/storage.py::save_json. The S3ArtifactStorage
tests inject a fake in-memory client (see FakeS3Client below) rather than
touching boto3 or any real network -- per this milestone's "no real cloud
resources required in unit tests" instruction.
"""

import json

import pytest

from research.artifact_storage import (
    ARTIFACT_ROOT,
    LocalArtifactStorage,
    S3ArtifactStorage,
    check_artifact_storage_health,
    is_production,
    raise_if_exists,
    resolve_artifact_storage,
    resolve_object_storage_config_from_env,
    to_artifact_key,
)
from research.storage import save_json


class _NotFound(Exception):
    def __init__(self, code="NoSuchKey"):
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    """In-memory stand-in for a boto3 S3 client -- just enough of the
    real surface (put_object/get_object/head_object/list_objects_v2) to
    drive S3ArtifactStorage's logic without any network call."""

    def __init__(self, reachable: bool = True):
        self.objects = {}
        self.reachable = reachable

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = Body if isinstance(Body, bytes) else Body.encode("utf-8")

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise _NotFound()
        return {"Body": _FakeBody(self.objects[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise _NotFound("404")
        return {}

    def list_objects_v2(self, Bucket, Prefix):
        matching = [{"Key": k} for k in self.objects if k.startswith(Prefix)]
        return {"Contents": matching}

    def head_bucket(self, Bucket):
        if not self.reachable:
            raise _NotFound("404")
        return {}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


class _FakeBody:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


# ---------------------------------------------------------------------
# LocalArtifactStorage
# ---------------------------------------------------------------------

def test_local_write_and_read_json_roundtrip(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_json("dfs_input/2026-08-19/pool.json", {"ok": True})
    assert storage.read_json("dfs_input/2026-08-19/pool.json") == {"ok": True}


def test_local_write_json_refuses_to_overwrite_by_default(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_json("x.json", {"a": 1})
    with pytest.raises(FileExistsError):
        storage.write_json("x.json", {"a": 2})
    # the original content is untouched
    assert storage.read_json("x.json") == {"a": 1}


def test_local_write_json_allow_overwrite_true_replaces_content(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_json("x.json", {"a": 1})
    storage.write_json("x.json", {"a": 2}, allow_overwrite=True)
    assert storage.read_json("x.json") == {"a": 2}


def test_local_read_json_returns_none_for_missing_file(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    assert storage.read_json("does/not/exist.json") is None


def test_local_read_json_returns_none_for_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{not valid json", encoding="utf-8")
    storage = LocalArtifactStorage(tmp_path)
    assert storage.read_json("bad.json") is None


def test_local_exists(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_json("present.json", {})
    assert storage.exists("present.json") is True
    assert storage.exists("absent.json") is False


def test_local_list_files_sorted_filtered_and_empty_for_missing_dir(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_json("snapshots/2026-08-19/snap_2.json", {})
    storage.write_json("snapshots/2026-08-19/snap_1.json", {})
    storage.write_json("snapshots/2026-08-19/other.json", {})
    files = storage.list_files("snapshots/2026-08-19", "snap_")
    assert [f.split("/")[-1] for f in files] == ["snap_1.json", "snap_2.json"]
    assert storage.list_files("no/such/dir", "x_") == []


def test_local_copy_file_refuses_overwrite(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    storage = LocalArtifactStorage(tmp_path / "dest_root")
    storage.copy_file(source, "raw/DKSalaries_1.csv")
    assert storage.exists("raw/DKSalaries_1.csv")
    with pytest.raises(FileExistsError):
        storage.copy_file(source, "raw/DKSalaries_1.csv")


# ---------------------------------------------------------------------
# S3ArtifactStorage (fake client -- no boto3, no network)
# ---------------------------------------------------------------------

def _s3_storage():
    return S3ArtifactStorage(
        bucket="bigmoney-artifacts", region="auto",
        access_key_id="ak", secret_access_key="sk",
        client=FakeS3Client(),
    )


def test_s3_write_and_read_json_roundtrip():
    storage = _s3_storage()
    storage.write_json("dfs_input/2026-08-19/pool.json", {"ok": True})
    assert storage.read_json("dfs_input/2026-08-19/pool.json") == {"ok": True}


def test_s3_write_json_refuses_to_overwrite_by_default():
    storage = _s3_storage()
    storage.write_json("x.json", {"a": 1})
    with pytest.raises(FileExistsError):
        storage.write_json("x.json", {"a": 2})


def test_s3_write_json_allow_overwrite_true_replaces_content():
    storage = _s3_storage()
    storage.write_json("x.json", {"a": 1})
    storage.write_json("x.json", {"a": 2}, allow_overwrite=True)
    assert storage.read_json("x.json") == {"a": 2}


def test_s3_read_json_returns_none_for_missing_key():
    storage = _s3_storage()
    assert storage.read_json("missing.json") is None


def test_s3_exists_true_and_false():
    storage = _s3_storage()
    storage.write_json("present.json", {})
    assert storage.exists("present.json") is True
    assert storage.exists("absent.json") is False


def test_s3_list_files_builds_correct_prefix_and_filters_ext():
    storage = _s3_storage()
    storage.write_json("snapshots/2026-08-19/snap_1.json", {})
    storage.write_json("snapshots/2026-08-19/snap_2.json", {})
    storage._client.objects["snapshots/2026-08-19/snap_1.txt"] = b"ignored"
    files = storage.list_files("snapshots/2026-08-19", "snap_")
    assert files == ["snapshots/2026-08-19/snap_1.json", "snapshots/2026-08-19/snap_2.json"]


def test_s3_copy_file_refuses_overwrite(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    storage = _s3_storage()
    storage.copy_file(source, "raw/DKSalaries_1.csv")
    assert storage.exists("raw/DKSalaries_1.csv")
    with pytest.raises(FileExistsError):
        storage.copy_file(source, "raw/DKSalaries_1.csv")


# ---------------------------------------------------------------------
# resolve_object_storage_config_from_env / resolve_artifact_storage
# ---------------------------------------------------------------------

def test_resolve_object_storage_config_none_when_unconfigured(monkeypatch):
    for key in ["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY", "OBJECT_STORAGE_ENDPOINT"]:
        monkeypatch.delenv(key, raising=False)
    assert resolve_object_storage_config_from_env() is None


def test_resolve_object_storage_config_full_when_all_required_vars_set(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_REGION", "auto")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "bkt")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY", "ak")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_KEY", "sk")
    monkeypatch.delenv("OBJECT_STORAGE_ENDPOINT", raising=False)
    config = resolve_object_storage_config_from_env()
    assert config == {"region": "auto", "bucket": "bkt", "access_key_id": "ak", "secret_access_key": "sk", "endpoint_url": None}


def test_resolve_object_storage_config_partial_is_none(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_REGION", "auto")
    monkeypatch.delenv("OBJECT_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_ACCESS_KEY", raising=False)
    monkeypatch.delenv("OBJECT_STORAGE_SECRET_KEY", raising=False)
    assert resolve_object_storage_config_from_env() is None


def test_resolve_artifact_storage_falls_back_to_local_when_unconfigured(tmp_path, monkeypatch):
    for key in ["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"]:
        monkeypatch.delenv(key, raising=False)
    storage = resolve_artifact_storage(tmp_path)
    assert isinstance(storage, LocalArtifactStorage)
    assert storage.root == tmp_path


def test_resolve_artifact_storage_selects_s3_when_fully_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_REGION", "auto")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "bkt")
    monkeypatch.setenv("OBJECT_STORAGE_ACCESS_KEY", "ak")
    monkeypatch.setenv("OBJECT_STORAGE_SECRET_KEY", "sk")
    storage = resolve_artifact_storage(tmp_path)
    assert isinstance(storage, S3ArtifactStorage)
    assert storage.bucket == "bkt"


# ---------------------------------------------------------------------
# research/storage.py::save_json still behaves exactly as before --
# creates parent dirs, overwrites silently, no exception.
# ---------------------------------------------------------------------

def test_save_json_still_creates_parent_dirs_and_overwrites_silently(tmp_path):
    target = tmp_path / "nested" / "dir" / "out.json"
    save_json(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    save_json(target, {"a": 2})  # must NOT raise -- preserves pre-Milestone-30 behavior
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}


# ---------------------------------------------------------------------
# Milestone 33.2: to_artifact_key
# ---------------------------------------------------------------------

def test_to_artifact_key_converts_absolute_path_under_root_to_relative_posix_key():
    absolute = ARTIFACT_ROOT / "dfs_input" / "2026-08-19" / "pool.json"
    assert to_artifact_key(absolute) == "dfs_input/2026-08-19/pool.json"


def test_to_artifact_key_accepts_an_already_relative_path():
    from pathlib import Path

    assert to_artifact_key(Path("dfs_input") / "2026-08-19" / "pool.json") == "dfs_input/2026-08-19/pool.json"


def test_to_artifact_key_falls_back_to_absolute_string_outside_the_artifact_root(tmp_path):
    outside = tmp_path / "scratch.json"
    key = to_artifact_key(outside)
    assert key == str(outside.resolve())


# ---------------------------------------------------------------------
# Milestone 33.2: raise_if_exists -- the shared, storage-aware overwrite
# guard every persistence module's local _no_overwrite() now delegates to.
# ---------------------------------------------------------------------

def test_raise_if_exists_is_storage_aware_not_local_disk_only(monkeypatch):
    # A path that has nothing on LOCAL disk but DOES exist in the
    # resolved storage backend must still be refused -- this is the
    # exact bug the old `if path.exists(): raise ...` local-only checks
    # had (silently blind to real collisions once object storage is
    # configured).
    storage = _s3_storage()
    storage.write_json("dfs_input/2026-08-19/pool.json", {"a": 1})
    monkeypatch.setattr("research.artifact_storage.resolve_artifact_storage", lambda root: storage)
    with pytest.raises(FileExistsError):
        raise_if_exists(ARTIFACT_ROOT / "dfs_input" / "2026-08-19" / "pool.json")


def test_raise_if_exists_does_not_raise_for_a_genuinely_new_path(monkeypatch):
    storage = _s3_storage()
    monkeypatch.setattr("research.artifact_storage.resolve_artifact_storage", lambda root: storage)
    raise_if_exists(ARTIFACT_ROOT / "dfs_input" / "2026-08-19" / "brand_new.json")  # must not raise


# ---------------------------------------------------------------------
# Milestone 33.2: write_bytes / write_text / read_bytes / delete
# ---------------------------------------------------------------------

def test_local_write_bytes_read_bytes_roundtrip(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_bytes("raw/DKSalaries.csv", b"a,b,c\n1,2,3\n")
    assert storage.read_bytes("raw/DKSalaries.csv") == b"a,b,c\n1,2,3\n"


def test_local_write_bytes_refuses_overwrite_by_default(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_bytes("x.bin", b"one")
    with pytest.raises(FileExistsError):
        storage.write_bytes("x.bin", b"two")


def test_local_write_text_read_bytes_roundtrip(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_text("lineups/2026-08-19/dk_lineups_1.csv", "a,b\n1,2\n")
    assert storage.read_bytes("lineups/2026-08-19/dk_lineups_1.csv") == b"a,b\n1,2\n"


def test_local_read_bytes_returns_none_for_missing_file(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    assert storage.read_bytes("does/not/exist.bin") is None


def test_local_delete_removes_file_and_is_a_noop_when_already_gone(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.write_bytes("x.bin", b"one")
    storage.delete("x.bin")
    assert storage.exists("x.bin") is False
    storage.delete("x.bin")  # must not raise


def test_s3_write_bytes_read_bytes_roundtrip():
    storage = _s3_storage()
    storage.write_bytes("raw/DKSalaries.csv", b"a,b,c\n1,2,3\n")
    assert storage.read_bytes("raw/DKSalaries.csv") == b"a,b,c\n1,2,3\n"


def test_s3_write_bytes_refuses_overwrite_by_default():
    storage = _s3_storage()
    storage.write_bytes("x.bin", b"one")
    with pytest.raises(FileExistsError):
        storage.write_bytes("x.bin", b"two")


def test_s3_read_bytes_returns_none_for_missing_key():
    storage = _s3_storage()
    assert storage.read_bytes("missing.bin") is None


def test_s3_delete_removes_object_and_is_a_noop_when_already_gone():
    storage = _s3_storage()
    storage.write_bytes("x.bin", b"one")
    storage.delete("x.bin")
    assert storage.exists("x.bin") is False
    storage.delete("x.bin")  # must not raise (S3 DeleteObject is itself a no-op for a missing key)


# ---------------------------------------------------------------------
# Milestone 33.2 Part 21: check_artifact_storage_health
# ---------------------------------------------------------------------

def test_check_storage_health_reports_local_when_unconfigured(tmp_path, monkeypatch):
    for key in ["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    result = check_artifact_storage_health(tmp_path)
    assert result["backend"] == "local"
    assert result["connectivity"] == "healthy"
    assert result["bucket"] is None


def test_check_storage_health_reports_not_configured_in_production_without_object_storage(tmp_path, monkeypatch):
    for key in ["OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NODE_ENV", "production")
    monkeypatch.delenv("ALLOW_LOCAL_STORAGE_IN_PRODUCTION", raising=False)
    assert is_production() is True
    result = check_artifact_storage_health(tmp_path)
    assert result["backend"] == "object"
    assert result["connectivity"] == "not_configured"
    assert result["bucket"] is None


def test_check_storage_health_reports_healthy_when_bucket_reachable(monkeypatch):
    fake_storage = _s3_storage()
    monkeypatch.setattr("research.artifact_storage.resolve_artifact_storage", lambda root: fake_storage)
    result = check_artifact_storage_health()
    assert result["backend"] == "object"
    assert result["connectivity"] == "healthy"
    assert result["bucket"] == "bigmoney-artifacts"


def test_check_storage_health_reports_unreachable_when_bucket_unreachable(monkeypatch):
    fake_storage = S3ArtifactStorage(
        bucket="bigmoney-artifacts", region="auto", access_key_id="ak", secret_access_key="sk",
        client=FakeS3Client(reachable=False),
    )
    monkeypatch.setattr("research.artifact_storage.resolve_artifact_storage", lambda root: fake_storage)
    result = check_artifact_storage_health()
    assert result["backend"] == "object"
    assert result["connectivity"] == "unreachable"
    assert result["bucket"] == "bigmoney-artifacts"


# ---------------------------------------------------------------------
# Milestone 33.2 Part 19: restart-safety simulation. Neither
# implementation holds any client-side cache of artifact CONTENT (only
# a connection/root) -- a fresh instance built AFTER an old one goes out
# of scope (simulating a process restart) must still resolve every
# artifact the old instance persisted, with zero special "reload" step.
# ---------------------------------------------------------------------

def test_local_restart_safety_a_fresh_instance_resolves_what_an_old_instance_persisted(tmp_path):
    first_process = LocalArtifactStorage(tmp_path)
    first_process.write_json("predictions/2026-08-19/pitcher_board_1.json", {"generated_at": "2026-08-19T12:00:00Z"})
    del first_process  # simulates the process exiting

    second_process = LocalArtifactStorage(tmp_path)  # a fresh "restart"
    assert second_process.read_json("predictions/2026-08-19/pitcher_board_1.json") == {"generated_at": "2026-08-19T12:00:00Z"}
    assert second_process.list_files("predictions/2026-08-19", "pitcher_board_") == ["predictions/2026-08-19/pitcher_board_1.json"]


def test_s3_restart_safety_a_fresh_instance_resolves_what_an_old_instance_persisted():
    # The FakeS3Client stands in for the real bucket -- shared across
    # both instances the same way a real S3-compatible bucket is shared
    # across two real process lifetimes, while each S3ArtifactStorage
    # object itself (the thing that gets torn down "at restart") holds
    # no cached artifact content of its own.
    bucket = FakeS3Client()
    first_process = S3ArtifactStorage(bucket="bigmoney-artifacts", region="auto", access_key_id="ak", secret_access_key="sk", client=bucket)
    first_process.write_json("predictions/2026-08-19/pitcher_board_1.json", {"generated_at": "2026-08-19T12:00:00Z"})
    del first_process

    second_process = S3ArtifactStorage(bucket="bigmoney-artifacts", region="auto", access_key_id="ak", secret_access_key="sk", client=bucket)
    assert second_process.read_json("predictions/2026-08-19/pitcher_board_1.json") == {"generated_at": "2026-08-19T12:00:00Z"}


# ---------------------------------------------------------------------
# Milestone 33.2 Part 20: multi-process (WEB + WORKER) shared-storage
# simulation. Two independent storage instances, each with its OWN
# local scratch directory nobody else touches, must both see the SAME
# authoritative artifact through the shared object-storage bucket alone
# -- proving a "WEB" reader never depends on "WORKER" local disk.
# ---------------------------------------------------------------------

def test_web_and_worker_processes_see_the_same_artifact_through_shared_object_storage_only(tmp_path):
    shared_bucket = FakeS3Client()

    worker_object_storage = S3ArtifactStorage(bucket="bigmoney-artifacts", region="auto", access_key_id="ak", secret_access_key="sk", client=shared_bucket)
    worker_local_scratch = LocalArtifactStorage(tmp_path / "worker_only_local_disk")

    web_object_storage = S3ArtifactStorage(bucket="bigmoney-artifacts", region="auto", access_key_id="ak", secret_access_key="sk", client=shared_bucket)
    web_local_scratch = LocalArtifactStorage(tmp_path / "web_only_local_disk")

    # WORKER "processes a slate": writes the real artifact to the shared
    # bucket, and (incidentally, as every real pipeline run does) also
    # touches its OWN local disk for something WEB must never depend on.
    worker_object_storage.write_json("native_projection_snapshots/2026-08-19/native_projection_1.json", {"player_count": 250})
    worker_local_scratch.write_json("scratch/tmp_intermediate.json", {"do_not_read_me": True})

    # WEB reads the published artifact through the SHARED bucket alone.
    assert web_object_storage.read_json("native_projection_snapshots/2026-08-19/native_projection_1.json") == {"player_count": 250}

    # WEB's own local disk was never touched by WORKER, and WEB never
    # needed it -- proving the read above didn't secretly depend on
    # local filesystem sharing (which local dev has, but a real hosted
    # multi-machine deployment does not).
    assert web_local_scratch.exists("scratch/tmp_intermediate.json") is False
    assert web_object_storage.exists("scratch/tmp_intermediate.json") is False  # WORKER's scratch file never reached the shared bucket either
