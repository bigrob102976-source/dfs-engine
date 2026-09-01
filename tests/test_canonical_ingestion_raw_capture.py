"""M2B / M2M -- canonical RAW R2 storage tests."""

import pytest

from canonical_ingestion.raw_capture import (
    EmptyRawCaptureError,
    RawCaptureRecorder,
    find_latest_raw_hash,
    write_raw_capture,
)
from research.artifact_storage import LocalArtifactStorage


def _storage(tmp_path):
    return LocalArtifactStorage(tmp_path)


def _recorder_with(*pairs):
    r = RawCaptureRecorder()
    for url, body in pairs:
        r.record(url, body)
    return r


def test_exact_bytes_hash_deterministic(tmp_path):
    storage = _storage(tmp_path)
    recorder = _recorder_with(
        ("https://api.draftkings.com/draftgroups/v1/draftgroups/152904/draftables", '{"a":1}'),
    )
    result_a = write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="152904", recorder=recorder, fetched_at="2026-08-31T20:00:00.000000+00:00")

    storage2 = _storage(tmp_path)
    recorder2 = _recorder_with(
        ("https://api.draftkings.com/draftgroups/v1/draftgroups/152904/draftables", '{"a":1}'),
    )
    result_b = write_raw_capture(storage2, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="152905", recorder=recorder2, fetched_at="2026-08-31T20:05:00.000000+00:00")

    # Identical captured bytes -> identical per-manifest rawHash, even
    # under a different providerSlateId/timestamp.
    assert result_a.raw_hash == result_b.raw_hash


def test_one_byte_change_different_hash(tmp_path):
    storage = _storage(tmp_path)
    r1 = _recorder_with(("https://x/draftables", '{"a":1}'))
    r2 = _recorder_with(("https://x/draftables", '{"a":2}'))
    result_a = write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="1", recorder=r1, fetched_at="2026-08-31T20:00:00.000000+00:00")
    result_b = write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="2", recorder=r2, fetched_at="2026-08-31T20:00:00.000000+00:00")
    assert result_a.raw_hash != result_b.raw_hash


def test_exact_bytes_are_verifiable_per_file(tmp_path):
    storage = _storage(tmp_path)
    body = '{"draftables":[{"id":1}]}'
    recorder = _recorder_with(("https://api.draftkings.com/draftgroups/v1/draftgroups/152904/draftables", body))
    result = write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="152904", recorder=recorder, fetched_at="2026-08-31T20:00:00.000000+00:00")

    assert len(result.file_keys) == 1
    stored_bytes = storage.read_bytes(result.file_keys[0])
    assert stored_bytes == body.encode("utf-8")  # exact bytes, not a re-serialized/re-formatted copy

    manifest = storage.read_json(result.manifest_key)
    assert manifest["files"][0]["name"] == "draftables"
    assert manifest["files"][0]["byteLength"] == len(body.encode("utf-8"))


def test_immutable_write_refuses_overwrite(tmp_path):
    storage = _storage(tmp_path)
    recorder = _recorder_with(("https://x/draftables", '{"a":1}'))
    write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="1", recorder=recorder, fetched_at="2026-08-31T20:00:00.000000+00:00")
    with pytest.raises(FileExistsError):
        write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="1", recorder=recorder, fetched_at="2026-08-31T20:00:00.000000+00:00")


def test_duplicate_identical_payload_detected_via_raw_hash(tmp_path):
    storage = _storage(tmp_path)
    recorder1 = _recorder_with(("https://x/draftables", '{"a":1}'))
    result1 = write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="1", recorder=recorder1, fetched_at="2026-08-31T20:00:00.000000+00:00")
    assert result1.is_duplicate_of_latest is False

    recorder2 = _recorder_with(("https://x/draftables", '{"a":1}'))
    result2 = write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="1", recorder=recorder2, fetched_at="2026-08-31T20:05:00.000000+00:00")
    assert result2.is_duplicate_of_latest is True
    assert result2.raw_hash == result1.raw_hash


def test_never_relabels_normalized_data_as_raw_empty_capture_refused(tmp_path):
    # An empty recorder means no real bytes were ever captured -- this
    # must refuse rather than write a hollow/fabricated "raw" record.
    storage = _storage(tmp_path)
    empty = RawCaptureRecorder()
    with pytest.raises(EmptyRawCaptureError):
        write_raw_capture(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="1", recorder=empty, fetched_at="2026-08-31T20:00:00.000000+00:00")


def test_find_latest_raw_hash_none_when_nothing_captured_yet(tmp_path):
    storage = _storage(tmp_path)
    assert find_latest_raw_hash(storage, sport="MLB", slate_date="2026-08-31", provider="draftkings_unofficial", provider_slate_id="999") is None
