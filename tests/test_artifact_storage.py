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
    LocalArtifactStorage,
    S3ArtifactStorage,
    resolve_artifact_storage,
    resolve_object_storage_config_from_env,
)
from research.storage import save_json


class _NotFound(Exception):
    def __init__(self, code="NoSuchKey"):
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    """In-memory stand-in for a boto3 S3 client -- just enough of the
    real surface (put_object/get_object/head_object/list_objects_v2) to
    drive S3ArtifactStorage's logic without any network call."""

    def __init__(self):
        self.objects = {}

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
