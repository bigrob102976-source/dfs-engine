"""Milestone 33.5: tests for scripts/smoke_test_object_storage.py's
run_smoke_test() -- the pure, storage-injectable core of the production
object-storage connectivity smoke test. Uses the SAME FakeS3Client
pattern as tests/test_artifact_storage.py (in-memory stand-in for a
boto3 client, no real network) -- per this project's "no real cloud
resources required in unit tests" convention.
"""

import importlib.util
import sys
from pathlib import Path

from research.artifact_storage import S3ArtifactStorage

# scripts/ is not a package (no __init__.py, matches every other
# scripts/*.py this repo's own tests import this same way).
_SPEC = importlib.util.spec_from_file_location(
    "smoke_test_object_storage", Path(__file__).resolve().parent.parent / "scripts" / "smoke_test_object_storage.py"
)
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["smoke_test_object_storage"] = _MODULE
_SPEC.loader.exec_module(_MODULE)
run_smoke_test = _MODULE.run_smoke_test

from tests.test_artifact_storage import FakeS3Client  # noqa: E402


def _storage(reachable: bool = True) -> S3ArtifactStorage:
    return S3ArtifactStorage(
        bucket="test-bucket", region="auto", access_key_id="x", secret_access_key="y", client=FakeS3Client(reachable=reachable)
    )


def test_full_round_trip_all_steps_pass():
    storage = _storage()
    result = run_smoke_test(storage, "healthchecks/r2-smoke-test.txt", do_write=True, do_cleanup=True)
    assert result["all_ok"] is True
    for step in ("write", "head", "read", "verify_contents", "delete", "verify_deletion"):
        assert result["steps"][step]["ok"] is True, result["steps"][step]


def test_write_leaves_the_object_readable_when_cleanup_is_skipped():
    storage = _storage()
    result = run_smoke_test(storage, "healthchecks/r2-smoke-test.txt", do_write=True, do_cleanup=False)
    assert result["all_ok"] is True
    assert "delete" not in result["steps"]
    assert "verify_deletion" not in result["steps"]
    # the object genuinely still exists in the fake backend afterward
    assert storage.exists("healthchecks/r2-smoke-test.txt") is True


def test_cleanup_only_deletes_a_previously_written_object():
    storage = _storage()
    storage.write_text("healthchecks/r2-smoke-test.txt", '{"smoke_test": true}', allow_overwrite=True)
    result = run_smoke_test(storage, "healthchecks/r2-smoke-test.txt", do_write=False, do_cleanup=True)
    assert result["all_ok"] is True
    assert result["steps"]["delete"]["ok"] is True
    assert result["steps"]["verify_deletion"]["ok"] is True
    assert storage.exists("healthchecks/r2-smoke-test.txt") is False


def test_verify_contents_fails_if_the_read_back_bytes_dont_match_what_was_written():
    storage = _storage()
    result = run_smoke_test(storage, "healthchecks/r2-smoke-test.txt", do_write=True, do_cleanup=False)
    assert result["steps"]["verify_contents"]["ok"] is True
    # simulate a corrupted/overwritten object between write and this check
    storage._client.objects["healthchecks/r2-smoke-test.txt"] = b"not the same content"  # noqa: SLF001
    result2 = run_smoke_test(storage, "healthchecks/r2-smoke-test.txt", do_write=False, do_cleanup=False)
    assert result2["all_ok"] is True  # do_write False and do_cleanup False means no steps ran at all
    assert result2["steps"] == {}


def test_write_step_reports_the_exact_error_and_stops_without_raising():
    class BrokenClient(FakeS3Client):
        def put_object(self, Bucket, Key, Body, **kwargs):
            raise RuntimeError("AccessDenied: not authorized to perform s3:PutObject")

    storage = S3ArtifactStorage(bucket="test-bucket", region="auto", access_key_id="x", secret_access_key="y", client=BrokenClient())
    result = run_smoke_test(storage, "healthchecks/r2-smoke-test.txt", do_write=True, do_cleanup=True)
    assert result["all_ok"] is False
    assert result["steps"]["write"]["ok"] is False
    assert "AccessDenied" in result["steps"]["write"]["error"]
    # never got to head/read/delete once write failed
    assert "head" not in result["steps"]


def test_head_step_reports_false_but_does_not_raise_when_head_object_errors_unexpectedly():
    class FlakyHeadClient(FakeS3Client):
        def head_object(self, Bucket, Key):
            raise RuntimeError("InternalError: 500")

    storage = S3ArtifactStorage(bucket="test-bucket", region="auto", access_key_id="x", secret_access_key="y", client=FlakyHeadClient())
    result = run_smoke_test(storage, "healthchecks/r2-smoke-test.txt", do_write=True, do_cleanup=False)
    assert result["steps"]["head"]["ok"] is False
    assert "InternalError" in result["steps"]["head"]["error"]
