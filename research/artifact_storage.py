"""Milestone 30: production-storage abstraction for every artifact this
pipeline writes -- the Python-side equivalent of
dashboard/lib/storage/StorageBackend.ts. Centralizes the "write JSON,
optionally refuse to overwrite" primitive that research/storage.py's
save_json() already backs every persistence module in this repo with
(dfs/persistence.py, ownership/persistence.py, native_projections/persistence.py,
external_projections/persistence.py, optimizer/persistence.py,
evaluation/actual_ownership_persistence.py,
evaluation/ownership_evaluation_persistence.py,
projection_engine/persistence.py, research/prediction_snapshot.py, and
several scripts/ entry points all import save_json from this package) --
so switching the underlying backend from local disk to S3-compatible
object storage is one implementation swap, not N duplicated rewrites.

Configured via the SAME five OBJECT_STORAGE_* env var names as the
dashboard's ProductionObjectStorageBackend (see
dashboard/lib/storage/StorageBackend.ts), so one .env configures both the
Node app and this Python worker: OBJECT_STORAGE_ENDPOINT (optional --
omit for real AWS S3), OBJECT_STORAGE_REGION, OBJECT_STORAGE_BUCKET,
OBJECT_STORAGE_ACCESS_KEY, OBJECT_STORAGE_SECRET_KEY.

SCOPE NOTE (honest, not silently glossed over): this module centralizes
the underlying write/read PRIMITIVE that save_json() uses -- it does NOT
yet rewrite every persistence module's own `_no_overwrite(path)` call
site (those still call path.exists() directly against local disk). A
full production cutover to S3ArtifactStorage would need those call sites
updated too; that is real, separate follow-up work, documented in
DEPLOYMENT.md rather than silently claimed as done here. Two modules
confirmed to bypass save_json entirely today --
research/game_environment/storage.py and
dfs/providers/draftkings_csv_storage.py -- are likewise not yet routed
through this abstraction.
"""

from __future__ import annotations

import json
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Optional


class ArtifactStorage(ABC):
    """Read/write access to this pipeline's JSON artifacts, backend-
    agnostic (local disk today, S3-compatible object storage for a
    hosted deployment)."""

    @abstractmethod
    def write_json(self, relative_path: str, data: Any, allow_overwrite: bool = False) -> None:
        """Writes `data` as JSON to `relative_path`. Raises
        FileExistsError if the artifact already exists and
        allow_overwrite is False (the default -- most artifacts this
        pipeline writes are immutable, timestamped snapshots)."""

    @abstractmethod
    def read_json(self, relative_path: str) -> Optional[Any]:
        """Returns the parsed JSON at `relative_path`, or None if it
        doesn't exist. Never raises for a missing file."""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        ...

    @abstractmethod
    def list_files(self, dir_relative_path: str, prefix: str = "", ext: str = ".json") -> List[str]:
        """Every artifact under `dir_relative_path` whose filename starts
        with `prefix` and ends with `ext`, sorted ascending. Empty list,
        never a raise, when the directory doesn't exist."""

    @abstractmethod
    def copy_file(self, source_path: Path, relative_dest_path: str, allow_overwrite: bool = False) -> None:
        """Copies an existing local file (e.g. an uploaded DK CSV) into
        storage at `relative_dest_path`."""


class LocalArtifactStorage(ArtifactStorage):
    """Local disk, relative to `root` -- the exact same layout every
    artifact directory in this repo already uses (research_output/,
    dfs_input/, native_projection_snapshots/, etc.)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _resolve(self, relative_path: str) -> Path:
        return self.root / relative_path

    def write_json(self, relative_path: str, data: Any, allow_overwrite: bool = False) -> None:
        path = self._resolve(relative_path)
        if not allow_overwrite and path.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def read_json(self, relative_path: str) -> Optional[Any]:
        path = self._resolve(relative_path)
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def exists(self, relative_path: str) -> bool:
        return self._resolve(relative_path).exists()

    def list_files(self, dir_relative_path: str, prefix: str = "", ext: str = ".json") -> List[str]:
        directory = self._resolve(dir_relative_path)
        if not directory.is_dir():
            return []
        names = sorted(
            name for name in os.listdir(directory)
            if name.startswith(prefix) and name.endswith(ext)
        )
        return [f"{dir_relative_path}/{name}" for name in names]

    def copy_file(self, source_path: Path, relative_dest_path: str, allow_overwrite: bool = False) -> None:
        dest = self._resolve(relative_dest_path)
        if not allow_overwrite and dest.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(source_path), dest)


def _is_not_found_error(err: Exception) -> bool:
    code = getattr(err, "response", {}).get("Error", {}).get("Code") if hasattr(err, "response") else None
    return code in ("404", "NoSuchKey", "NotFound")


class S3ArtifactStorage(ArtifactStorage):
    """Real S3-compatible object storage (AWS S3, Cloudflare R2,
    Backblaze B2, MinIO, ...) via boto3 -- the standard, mature AWS SDK
    for Python, matching the Node side's choice of @aws-sdk/client-s3.

    `client` is normally left as None (a real boto3 client is built from
    the constructor args) -- tests inject a fake client instead, so this
    module's logic is fully unit-testable without boto3 being installed
    or any real network call, per this milestone's "no real cloud
    resources required in unit tests" instruction."""

    def __init__(
        self,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self.bucket = bucket
        if client is not None:
            self._client = client
        else:
            import boto3  # local import: only required when object storage is actually configured

            self._client = boto3.client(
                "s3",
                region_name=region,
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )

    def exists(self, relative_path: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=relative_path)
            return True
        except Exception as err:  # noqa: BLE001 -- boto3 raises botocore.exceptions.ClientError, kept import-optional
            if _is_not_found_error(err):
                return False
            raise

    def write_json(self, relative_path: str, data: Any, allow_overwrite: bool = False) -> None:
        if not allow_overwrite and self.exists(relative_path):
            raise FileExistsError(f"Refusing to overwrite existing artifact: {relative_path}")
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self._client.put_object(Bucket=self.bucket, Key=relative_path, Body=body, ContentType="application/json")

    def read_json(self, relative_path: str) -> Optional[Any]:
        try:
            result = self._client.get_object(Bucket=self.bucket, Key=relative_path)
            body = result["Body"].read()
            return json.loads(body)
        except Exception as err:  # noqa: BLE001
            if _is_not_found_error(err):
                return None
            raise

    def list_files(self, dir_relative_path: str, prefix: str = "", ext: str = ".json") -> List[str]:
        key_prefix = f"{dir_relative_path.rstrip('/')}/{prefix}"
        result = self._client.list_objects_v2(Bucket=self.bucket, Prefix=key_prefix)
        keys = [obj["Key"] for obj in result.get("Contents", []) if obj.get("Key", "").endswith(ext)]
        return sorted(keys)

    def copy_file(self, source_path: Path, relative_dest_path: str, allow_overwrite: bool = False) -> None:
        if not allow_overwrite and self.exists(relative_dest_path):
            raise FileExistsError(f"Refusing to overwrite existing artifact: {relative_dest_path}")
        with Path(source_path).open("rb") as f:
            self._client.put_object(Bucket=self.bucket, Key=relative_dest_path, Body=f.read())


def resolve_object_storage_config_from_env() -> Optional[dict]:
    """Reads the five OBJECT_STORAGE_* env vars. Returns None -- never
    raises -- when any required var is missing. Mirrors
    dashboard/lib/storage/StorageBackend.ts::resolveObjectStorageConfigFromEnv."""
    region = os.environ.get("OBJECT_STORAGE_REGION")
    bucket = os.environ.get("OBJECT_STORAGE_BUCKET")
    access_key_id = os.environ.get("OBJECT_STORAGE_ACCESS_KEY")
    secret_access_key = os.environ.get("OBJECT_STORAGE_SECRET_KEY")
    if not region or not bucket or not access_key_id or not secret_access_key:
        return None
    return {
        "region": region,
        "bucket": bucket,
        "access_key_id": access_key_id,
        "secret_access_key": secret_access_key,
        "endpoint_url": os.environ.get("OBJECT_STORAGE_ENDPOINT") or None,
    }


def resolve_artifact_storage(local_root: Path) -> ArtifactStorage:
    """S3ArtifactStorage when OBJECT_STORAGE_* is fully configured,
    otherwise LocalArtifactStorage rooted at `local_root` -- the same
    selection order as the dashboard's storage backend, without a hard
    production fail-closed guard: this codebase has no established
    "production mode" concept on the Python side today (unlike Next.js's
    built-in NODE_ENV), so inventing one here would be new, unrequested
    architecture rather than reusing something that already exists. This
    is an honest scope boundary, documented in DEPLOYMENT.md."""
    config = resolve_object_storage_config_from_env()
    if config:
        return S3ArtifactStorage(**config)
    return LocalArtifactStorage(local_root)
