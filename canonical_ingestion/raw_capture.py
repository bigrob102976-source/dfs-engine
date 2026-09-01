"""M2B -- canonical RAW R2 storage.

Captures the EXACT bytes DraftKings' unofficial endpoints returned for
one slate fetch and writes them immutably through the existing
production object-storage abstraction (research/artifact_storage.py --
the same S3-capable module the live provider_slate_*.json artifacts
already use), under one FLAT directory per provider slate (matching
this project's existing timestamp-PREFIXED-filename convention, e.g.
dk_player_pool_{timestamp}.json, rather than a nested per-capture
subdirectory -- flat listing is what makes duplicate-hash lookups work
identically on both LocalArtifactStorage, whose list_files() is NOT
recursive across subdirectories, and S3ArtifactStorage, whose prefix
listing is):

    raw/{sport}/{slateDate}/{provider}/{providerSlateId}/{timestamp}_{endpoint}.json
    raw/{sport}/{slateDate}/{provider}/{providerSlateId}/{timestamp}_manifest.json

HONESTY NOTE (per this milestone's explicit instruction not to mislabel
normalized data as RAW): one canonical slate is assembled from SEVERAL
distinct DraftKings HTTP endpoints (contest discovery, draftables,
game-type rules) -- there is no single blob of "the slate's raw bytes"
to hash directly. Each individual file written here IS the exact,
byte-for-byte response DraftKings returned for its one endpoint
(verified in tests). `rawHash` is a SHA-256 over a deterministic
manifest of those per-file hashes (name + sha256, sorted by name) --
clearly a manifest checksum, not a claim that a single "raw response"
exists. Every per-file hash is independently exact-bytes-verifiable.

Byte-exact capture is only possible where this codebase actually
retains the wire bytes: draftkings_unofficial/client.py's `capture`
hook (M2B addition -- see that module's docstring), fired with the
exact decoded HTTP response body before any JSON parsing. This module
never reconstructs "raw" bytes by re-serializing an already-parsed
dict (that would violate this milestone's explicit anti-fabrication
rule) -- see RawCaptureRecorder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from canonical.hashing import compute_raw_hash
from research.artifact_storage import ArtifactStorage

RAW_MANIFEST_SCHEMA_VERSION = "raw_manifest_v1"


class RawCaptureRecorder:
    """Collects (url, exact_response_body_text) pairs as they're
    captured live from draftkings_unofficial/client.py's `capture` hook.
    Never raises from `record` -- a capture-recording bug must never be
    allowed to break a real DK fetch (client.py itself also guards this
    defensively; this is a second, independent floor)."""

    def __init__(self) -> None:
        self._entries: List[tuple] = []

    def record(self, url: str, body: str) -> None:
        try:
            self._entries.append((url, body))
        except Exception:  # noqa: BLE001
            pass

    @property
    def entries(self) -> List[tuple]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


_ENDPOINT_NAME_PATTERNS = (
    (re.compile(r"/sports/v1/sports"), "sports"),
    (re.compile(r"/lobby/getcontests"), "contests"),
    (re.compile(r"/draftgroups/v1/draftgroups/(\d+)/draftables"), "draftables"),
    (re.compile(r"/lineups/v1/gametypes/(\d+)/rules"), "rules_{0}"),
    (re.compile(r"/contests/v1/contests/(\d+)"), "contest_details_{0}"),
)


def _endpoint_name_for_url(url: str, index: int) -> str:
    """Derives a short, filesystem/object-key-safe label from a real DK
    endpoint URL (e.g. '.../draftgroups/v1/draftgroups/152904/draftables'
    -> 'draftables'). Falls back to a positional name for any URL that
    doesn't match a known pattern, rather than guessing -- this is a
    display/organization label only; `url` itself is always preserved
    verbatim in the manifest."""
    path = urlparse(url).path
    for pattern, template in _ENDPOINT_NAME_PATTERNS:
        match = pattern.search(path)
        if match:
            return template.format(*match.groups())
    return f"endpoint_{index}"


@dataclass
class RawCaptureFileRecord:
    name: str
    url: str
    sha256: str
    byte_length: int
    key: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "url": self.url, "sha256": self.sha256, "byteLength": self.byte_length, "key": self.key}


@dataclass
class RawCaptureWriteResult:
    raw_hash: str
    manifest_key: str
    file_keys: List[str] = field(default_factory=list)
    is_duplicate_of_latest: bool = False


class EmptyRawCaptureError(ValueError):
    """Raised when write_raw_capture is called with zero captured
    responses -- never writes an empty/fabricated RAW capture."""


def raw_capture_dir(sport: str, slate_date: str, provider: str, provider_slate_id: str) -> str:
    return f"raw/{sport}/{slate_date}/{provider}/{provider_slate_id}"


def _timestamp_tag(fetched_at: str) -> str:
    dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    return dt.strftime("%Y%m%dT%H%M%S%f")


def find_latest_raw_hash(
    storage: ArtifactStorage, *, sport: str, slate_date: str, provider: str, provider_slate_id: str,
) -> Optional[str]:
    """Best-effort lookup of the most recent prior RAW capture's
    rawHash for this exact provider slate, for duplicate-detection
    logging only (never gates whether a new RAW capture is written --
    RAW is always-append/immutable-history by design). Returns None,
    never raises, when nothing is found -- this is informational, not a
    correctness dependency. Works identically on both LocalArtifactStorage
    and S3ArtifactStorage because every capture's files (including its
    manifest) live FLAT in one directory, timestamp-PREFIXED, never
    nested in a per-run subdirectory -- see this module's own docstring."""
    directory = raw_capture_dir(sport, slate_date, provider, provider_slate_id)
    try:
        manifest_keys = storage.list_files(directory, prefix="", ext="manifest.json")
    except Exception:  # noqa: BLE001
        return None
    if not manifest_keys:
        return None
    latest_key = sorted(manifest_keys)[-1]
    manifest = storage.read_json(latest_key)
    if not manifest:
        return None
    return manifest.get("rawHash")


def write_raw_capture(
    storage: ArtifactStorage, *, sport: str, slate_date: str, provider: str, provider_slate_id: str,
    recorder: RawCaptureRecorder, fetched_at: str,
) -> RawCaptureWriteResult:
    """Writes every captured (url, exact_body) pair as its own immutable
    object, plus a manifest tying them together with a deterministic
    rawHash. Raises EmptyRawCaptureError if nothing was captured (e.g.
    the capture hook was never actually wired to a real fetch) --
    refuses to write a hollow RAW record."""
    entries = recorder.entries
    if not entries:
        raise EmptyRawCaptureError(
            f"No raw responses captured for {provider}:{provider_slate_id} -- refusing to write an empty RAW capture."
        )

    previous_hash = find_latest_raw_hash(storage, sport=sport, slate_date=slate_date, provider=provider, provider_slate_id=provider_slate_id)

    ts = _timestamp_tag(fetched_at)
    directory = raw_capture_dir(sport, slate_date, provider, provider_slate_id)

    files: List[RawCaptureFileRecord] = []
    used_names: Dict[str, int] = {}
    for index, (url, body) in enumerate(entries):
        body_bytes = body.encode("utf-8")
        sha = compute_raw_hash(body_bytes)
        base_name = _endpoint_name_for_url(url, index)
        count = used_names.get(base_name, 0)
        used_names[base_name] = count + 1
        name = base_name if count == 0 else f"{base_name}_{count}"
        key = f"{directory}/{ts}_{name}.json"
        storage.write_bytes(key, body_bytes, allow_overwrite=False)
        files.append(RawCaptureFileRecord(name=name, url=url, sha256=sha, byte_length=len(body_bytes), key=key))

    manifest_text = "\n".join(f"{f.name}\t{f.sha256}" for f in sorted(files, key=lambda f: f.name))
    raw_hash = compute_raw_hash(manifest_text.encode("utf-8"))

    manifest = {
        "schemaVersion": RAW_MANIFEST_SCHEMA_VERSION,
        "sport": sport,
        "slateDate": slate_date,
        "provider": provider,
        "providerSlateId": provider_slate_id,
        "fetchedAt": fetched_at,
        "files": [f.to_dict() for f in files],
        "rawHash": raw_hash,
    }
    manifest_key = f"{directory}/{ts}_manifest.json"
    storage.write_json(manifest_key, manifest, allow_overwrite=False)

    return RawCaptureWriteResult(
        raw_hash=raw_hash,
        manifest_key=manifest_key,
        file_keys=[f.key for f in files],
        is_duplicate_of_latest=(previous_hash is not None and previous_hash == raw_hash),
    )
