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

Milestone 33.2: save_json() now calls resolve_artifact_storage() itself
(not a hardcoded LocalArtifactStorage), so every one of the persistence
modules listed above gets S3-compatible object storage automatically
once OBJECT_STORAGE_* is configured -- no per-module call-site changes
needed. The two modules that bypassed save_json entirely
(research/game_environment/storage.py,
dfs/providers/draftkings_csv_storage.py) and the two CSV-writing call
sites (optimizer/persistence.py, evaluation/ownership_evaluation_persistence.py)
are now routed through this abstraction directly via the new
write_bytes/write_text/read_bytes methods.

PRODUCTION FAIL-CLOSED: mirrors dashboard/lib/storage/backend.ts's
resolveStorageBackend() -- Python has no NODE_ENV of its own, but every
Python process in this project is always spawned BY the Next.js
process (dashboard/lib/orchestrator/pythonRunner.ts's child_process.spawn
inherits the parent's environment by default), so NODE_ENV is already
the correct, single source of truth for "is this a production run" on
both sides. Production with OBJECT_STORAGE_* unset refuses to silently
fall back to local disk unless ALLOW_LOCAL_STORAGE_IN_PRODUCTION=true is
explicitly set (same flag name and semantics as the Node side).
"""

from __future__ import annotations

import json
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Optional

# Milestone 33.2: the ONE canonical artifact root every relative object
# key is computed against -- repo root, matching every existing artifact
# directory's own DEFAULT_*_ROOT convention (e.g.
# player_identity/persistence.py's
# `Path(__file__).resolve().parent.parent / "player_identity_snapshots"`)
# and the dashboard's getArtifactRoot() (dashboard/lib/artifactRoot.ts).
# Computed from this file's own location rather than Path.cwd() so it
# stays correct even if a caller's working directory is ever wrong --
# CLAUDE.md's "always run with the project root as cwd" convention is a
# process-invocation contract, not something this module should have to
# trust blindly.
ARTIFACT_ROOT = Path(__file__).resolve().parent.parent


def to_artifact_key(path: Path) -> str:
    """Converts an absolute (or already-relative) filesystem Path into
    the canonical, forward-slash, ARTIFACT_ROOT-relative object key both
    LocalArtifactStorage and S3ArtifactStorage expect. A Path that isn't
    under ARTIFACT_ROOT (e.g. a genuinely temporary scratch file) is
    returned as its resolved absolute string unchanged -- callers that
    pass such a path are choosing NOT to go through artifact storage, not
    hitting an error here."""
    path = Path(path)
    resolved = path if path.is_absolute() else (ARTIFACT_ROOT / path)
    try:
        relative = resolved.resolve().relative_to(ARTIFACT_ROOT)
    except ValueError:
        return str(resolved)
    return relative.as_posix()


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

    @abstractmethod
    def write_bytes(self, relative_path: str, data: bytes, allow_overwrite: bool = False) -> None:
        """Milestone 33.2: writes raw bytes already held in memory (e.g. an
        uploaded CSV's body) -- the in-memory counterpart to copy_file,
        for callers that never had the bytes on local disk in the first
        place. Same overwrite-refusal contract as write_json."""

    @abstractmethod
    def write_text(self, relative_path: str, text: str, allow_overwrite: bool = False) -> None:
        """Milestone 33.2: writes a plain-text artifact (e.g. a lineup-set
        CSV export) -- the non-JSON counterpart to write_json."""

    @abstractmethod
    def read_bytes(self, relative_path: str) -> Optional[bytes]:
        """Returns the raw bytes at `relative_path`, or None if it
        doesn't exist. Never raises for a missing file."""

    @abstractmethod
    def delete(self, relative_path: str) -> None:
        """Removes the artifact at `relative_path`. A no-op (never
        raises) when it doesn't exist -- deleting an already-gone
        artifact is the caller's intended end state either way. Used
        ONLY by explicit user/admin delete actions (e.g. removing an
        uploaded DK CSV) -- never as part of normal immutable-snapshot
        persistence, which never deletes anything."""


def _atomic_write_bytes(path: Path, data: bytes, allow_overwrite: bool) -> None:
    """MLB FILE LOCK / DUPLICATE ARTIFACT WRITER RACE hardening: the
    previous LocalArtifactStorage implementation did a plain
    `path.exists()` check followed by a SEPARATE `path.open("w")` --
    two concurrent writers could both pass the check before either
    wrote (a real TOCTOU race, confirmed live for the ownership writer
    -- see ownership/persistence.py's own top-of-file note), and even a
    single writer's plain `open("w")` truncates the file in place, so a
    reader could observe a genuinely partial/corrupt document mid-write.

    Fixed with two real OS-level atomicity guarantees instead of a
    Python-level check:
      - allow_overwrite=False: `os.open(..., O_CREAT | O_EXCL)` is an
        atomic "create only if it doesn't already exist" kernel
        operation -- there is no window between "check" and "create"
        because there is no separate check; the OS performs both as one
        indivisible step and raises FileExistsError itself if the name
        already exists.
      - allow_overwrite=True: write to a unique temp file in the SAME
        directory (guaranteeing the eventual rename is on the same
        filesystem, required for atomicity), flush, close, then
        `os.replace()` -- an atomic rename on both POSIX and Windows.
        A reader can only ever see the complete OLD file or the
        complete NEW file, never a partially-written one."""
    if not allow_overwrite:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        except BaseException:
            # A failure after the atomic create (e.g. disk full mid-write)
            # must not leave a half-written file masquerading as a real,
            # complete artifact -- clean it up and re-raise the real error.
            try:
                path.unlink()
            except OSError:
                pass
            raise
        return

    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{id(data)}")
    try:
        with tmp_path.open("wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(path))
    finally:
        # os.replace() already removed tmp_path on success; this only
        # cleans up a leftover temp file if the write/replace itself
        # failed partway through.
        try:
            tmp_path.unlink()
        except OSError:
            pass


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
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        _atomic_write_bytes(path, body, allow_overwrite=allow_overwrite)

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

    def write_bytes(self, relative_path: str, data: bytes, allow_overwrite: bool = False) -> None:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(path, data, allow_overwrite=allow_overwrite)

    def write_text(self, relative_path: str, text: str, allow_overwrite: bool = False) -> None:
        self.write_bytes(relative_path, text.encode("utf-8"), allow_overwrite=allow_overwrite)

    def read_bytes(self, relative_path: str) -> Optional[bytes]:
        path = self._resolve(relative_path)
        try:
            return path.read_bytes()
        except OSError:
            return None

    def delete(self, relative_path: str) -> None:
        path = self._resolve(relative_path)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


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

    def write_bytes(self, relative_path: str, data: bytes, allow_overwrite: bool = False) -> None:
        if not allow_overwrite and self.exists(relative_path):
            raise FileExistsError(f"Refusing to overwrite existing artifact: {relative_path}")
        self._client.put_object(Bucket=self.bucket, Key=relative_path, Body=data)

    def write_text(self, relative_path: str, text: str, allow_overwrite: bool = False) -> None:
        self.write_bytes(relative_path, text.encode("utf-8"), allow_overwrite=allow_overwrite)

    def read_bytes(self, relative_path: str) -> Optional[bytes]:
        try:
            result = self._client.get_object(Bucket=self.bucket, Key=relative_path)
            return result["Body"].read()
        except Exception as err:  # noqa: BLE001
            if _is_not_found_error(err):
                return None
            raise

    def delete(self, relative_path: str) -> None:
        # S3's DeleteObject is itself already a no-op (200 OK) for a
        # missing key -- no existence check needed first.
        self._client.delete_object(Bucket=self.bucket, Key=relative_path)


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


class ProductionStorageNotConfiguredError(Exception):
    """Raised when NODE_ENV=production (inherited from the parent
    Next.js process) but no OBJECT_STORAGE_* config and no explicit
    ALLOW_LOCAL_STORAGE_IN_PRODUCTION=true override exist -- mirrors
    dashboard/lib/storage/backend.ts::ProductionStorageNotConfiguredError
    exactly, including the flag name."""


ALLOW_LOCAL_STORAGE_IN_PRODUCTION_FLAG = "ALLOW_LOCAL_STORAGE_IN_PRODUCTION"


def is_production() -> bool:
    """NODE_ENV is set by (and inherited from) the parent Next.js
    process for every real Python invocation in this project -- see this
    module's own docstring for why that's the correct signal here rather
    than inventing a second one."""
    return os.environ.get("NODE_ENV") == "production"


def raise_if_exists(path: Path) -> None:
    """Milestone 33.2: the ONE shared, storage-aware replacement for the
    `_no_overwrite(path)` helper ~10 persistence modules each used to
    define locally -- every one of those local copies checked
    `path.exists()` against LOCAL DISK ONLY, which is silently wrong the
    moment OBJECT_STORAGE_* is configured (the real artifact lives in the
    bucket; local disk has nothing on it, so the check could never
    detect a genuine collision there). This version checks through
    resolve_artifact_storage(), so the immutability guarantee holds on
    both backends identically."""
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    key = to_artifact_key(path)
    if storage.exists(key):
        raise FileExistsError(f"Refusing to overwrite existing artifact: {key}")


def resolve_artifact_storage(local_root: Path) -> ArtifactStorage:
    """S3ArtifactStorage when OBJECT_STORAGE_* is fully configured,
    otherwise LocalArtifactStorage rooted at `local_root` -- the same
    selection order, and the same production fail-closed guard, as the
    dashboard's resolveStorageBackend(). Raises
    ProductionStorageNotConfiguredError instead of silently returning a
    per-process-local (and therefore, in a real multi-machine deployment,
    unshared) LocalArtifactStorage."""
    config = resolve_object_storage_config_from_env()
    if config:
        return S3ArtifactStorage(**config)
    if is_production():
        if os.environ.get(ALLOW_LOCAL_STORAGE_IN_PRODUCTION_FLAG) == "true":
            return LocalArtifactStorage(local_root)
        raise ProductionStorageNotConfiguredError(
            "OBJECT_STORAGE_REGION, OBJECT_STORAGE_BUCKET, OBJECT_STORAGE_ACCESS_KEY, and OBJECT_STORAGE_SECRET_KEY "
            "are required in production (a shared object-storage bucket) -- refusing to silently fall back to local "
            "disk, which would give the WEB process and this Python WORKER process disconnected, unrelated artifact "
            f"storage. Set the OBJECT_STORAGE_* variables, or explicitly set {ALLOW_LOCAL_STORAGE_IN_PRODUCTION_FLAG}=true "
            "if you understand the risk (e.g. a genuinely single-instance early deployment)."
        )
    return LocalArtifactStorage(local_root)


def check_artifact_storage_health(local_root: Path = ARTIFACT_ROOT) -> dict:
    """Milestone 33.2 Part 21: a SAFE (never a credential/endpoint value),
    non-destructive readiness snapshot -- mirrors
    dashboard/lib/systemReadiness.ts::getObjectStorageReadiness()'s exact
    shape/semantics so a Python-side caller (a diagnostic script, or a
    future admin cross-check) reports the identical thing the Node side
    already shows on /admin/system. Never raises for an expected
    "not configured" or "unreachable" state -- only a genuinely
    unexpected error propagates, same as the Node version's
    checkObjectStorageConnection(). HeadBucket only confirms the bucket
    is reachable with the configured credentials; it never depends on
    (or touches) any particular object."""
    try:
        storage = resolve_artifact_storage(local_root)
    except ProductionStorageNotConfiguredError as err:
        return {"backend": "object", "connectivity": "not_configured", "bucket": None, "detail": str(err)}

    if isinstance(storage, LocalArtifactStorage):
        return {"backend": "local", "connectivity": "healthy", "bucket": None, "detail": f"Local disk at {storage.root}."}

    try:
        storage._client.head_bucket(Bucket=storage.bucket)  # noqa: SLF001 -- this module owns S3ArtifactStorage
        return {"backend": "object", "connectivity": "healthy", "bucket": storage.bucket, "detail": f'Bucket "{storage.bucket}" reachable.'}
    except Exception as err:  # noqa: BLE001 -- boto3 raises botocore.exceptions.ClientError, kept import-optional
        return {"backend": "object", "connectivity": "unreachable", "bucket": storage.bucket, "detail": str(err)}
