"""Milestone 33.5: real production object-storage connectivity smoke
test -- write / head / read / verify / delete / verify-deletion against
whatever backend research/artifact_storage.py::resolve_artifact_storage()
actually resolves to in the CURRENT environment.

Uses ONLY the existing storage abstraction (S3ArtifactStorage's
write_text/exists/read_bytes/delete) -- no ad hoc boto3/S3 SDK code, so
this exercises exactly the same code path every real pipeline write goes
through, not a parallel one that could drift out of sync with it.

Prints a single sanitized JSON report to stdout and nothing else. Never
prints an access key, secret key, or DATABASE_URL -- the only storage
identifiers surfaced are backend kind, bucket name, region, and endpoint
host, mirroring the existing precedent set by
check_artifact_storage_health()'s own "safe" report shape.

Run from the repo root, in an environment where OBJECT_STORAGE_* is
already configured (this is meant to be run as a one-off command inside
the real WEB/WORKER service, e.g. via Railway's dashboard or CLI -- it
reads production credentials from the process environment, never from
arguments, so nothing sensitive ever appears on a command line or in
shell history):

    python scripts/smoke_test_object_storage.py            # full round trip, cleans up after itself
    python scripts/smoke_test_object_storage.py --no-cleanup   # write+verify, LEAVES the object in place
    python scripts/smoke_test_object_storage.py --cleanup-only # deletes+verifies deletion (pair with --no-cleanup)

The default key is healthchecks/r2-smoke-test.txt (override with
--key). Exits 0 if every requested step passed, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.artifact_storage import (  # noqa: E402
    ARTIFACT_ROOT,
    LocalArtifactStorage,
    ProductionStorageNotConfiguredError,
    S3ArtifactStorage,
    resolve_artifact_storage,
)

DEFAULT_KEY = "healthchecks/r2-smoke-test.txt"


def _payload(key: str) -> str:
    # Valid JSON text so BOTH this script's own read-back AND a
    # cross-language check from the Node side (getStorage().readJson())
    # can parse it -- every real artifact in this system is JSON, so
    # this is the realistic shape to test, not a distinguishing choice.
    return json.dumps(
        {
            "smoke_test": True,
            "source": "scripts/smoke_test_object_storage.py",
            "key": key,
            "generated_at_unix": time.time(),
        }
    )


def run_smoke_test(storage: S3ArtifactStorage, key: str, *, do_write: bool, do_cleanup: bool) -> dict[str, Any]:
    """Pure, storage-injectable core -- see tests/test_smoke_test_object_storage.py
    for the fake-client-driven test suite covering this function directly.
    `storage` must already be an S3ArtifactStorage; callers decide what to
    do (and how to report it) when resolve_artifact_storage() gives back
    something else instead -- see main()."""
    steps: dict[str, Any] = {}
    expected_body: str | None = None

    if do_write:
        expected_body = _payload(key)
        t0 = time.monotonic()
        try:
            storage.write_text(key, expected_body, allow_overwrite=True)
            steps["write"] = {"ok": True, "elapsed_ms": round((time.monotonic() - t0) * 1000, 1)}
        except Exception as err:  # noqa: BLE001 -- report the exact sanitized error, never raise past this point
            steps["write"] = {"ok": False, "error": str(err)}
            return {"steps": steps, "all_ok": False}

        t0 = time.monotonic()
        try:
            head_ok = storage.exists(key)
            steps["head"] = {"ok": head_ok, "elapsed_ms": round((time.monotonic() - t0) * 1000, 1)}
        except Exception as err:  # noqa: BLE001
            steps["head"] = {"ok": False, "error": str(err)}
            head_ok = False

        t0 = time.monotonic()
        try:
            raw = storage.read_bytes(key)
            read_ok = raw is not None
            steps["read"] = {"ok": read_ok, "elapsed_ms": round((time.monotonic() - t0) * 1000, 1)}
        except Exception as err:  # noqa: BLE001
            steps["read"] = {"ok": False, "error": str(err)}
            raw = None

        content_matches = raw is not None and raw.decode("utf-8") == expected_body
        steps["verify_contents"] = {"ok": content_matches}

    if do_cleanup:
        t0 = time.monotonic()
        try:
            storage.delete(key)
            steps["delete"] = {"ok": True, "elapsed_ms": round((time.monotonic() - t0) * 1000, 1)}
        except Exception as err:  # noqa: BLE001
            steps["delete"] = {"ok": False, "error": str(err)}

        t0 = time.monotonic()
        try:
            still_exists = storage.exists(key)
            steps["verify_deletion"] = {"ok": not still_exists, "elapsed_ms": round((time.monotonic() - t0) * 1000, 1)}
        except Exception as err:  # noqa: BLE001
            steps["verify_deletion"] = {"ok": False, "error": str(err)}

    all_ok = all(bool(s.get("ok")) for s in steps.values())
    return {"steps": steps, "all_ok": all_ok}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", default=DEFAULT_KEY)
    parser.add_argument("--no-cleanup", action="store_true", help="write+verify only, leave the object in place")
    parser.add_argument("--cleanup-only", action="store_true", help="skip write, only delete+verify deletion")
    args = parser.parse_args()

    report: dict[str, Any] = {"key": args.key}

    try:
        storage = resolve_artifact_storage(ARTIFACT_ROOT)
    except ProductionStorageNotConfiguredError as err:
        report.update({"backend_resolved": "not_configured", "error": str(err), "all_ok": False})
        print(json.dumps(report, indent=2))
        return 1

    if isinstance(storage, LocalArtifactStorage):
        # Exactly the "accidental local-disk fallback" this test exists
        # to catch -- report it plainly rather than silently testing the
        # wrong thing.
        report.update(
            {
                "backend_resolved": "local",
                "error": "resolve_artifact_storage() returned LocalArtifactStorage, not S3ArtifactStorage -- "
                "OBJECT_STORAGE_* is not fully configured in this environment.",
                "all_ok": False,
            }
        )
        print(json.dumps(report, indent=2))
        return 1

    assert isinstance(storage, S3ArtifactStorage)
    report["backend_resolved"] = "object"
    report["bucket"] = storage.bucket
    # Never the access key / secret key -- only non-secret identifiers,
    # matching check_artifact_storage_health()'s existing precedent.
    client_meta = getattr(storage._client, "meta", None)  # noqa: SLF001 -- read-only, diagnostic only
    if client_meta is not None:
        report["region"] = getattr(client_meta, "region_name", None)
        endpoint_url = getattr(client_meta, "endpoint_url", None)
        if endpoint_url:
            from urllib.parse import urlparse

            report["endpoint_host"] = urlparse(endpoint_url).hostname

    result = run_smoke_test(
        storage,
        args.key,
        do_write=not args.cleanup_only,
        do_cleanup=not args.no_cleanup,
    )
    report.update(result)
    print(json.dumps(report, indent=2))
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
