"""Milestone 32.1, Part 4 -- persistent raw-data cache.

Every cached payload gets TWO files: the raw payload itself
(<key>.json or <key>.csv) and a metadata sidecar (<key>.meta.json)
recording source/retrieved_at/requested range/record_count/schema info
-- exactly the fields Part 4 requires, kept separate from the payload
so re-reading the payload never has to parse metadata out of it.

Both files are written atomically (write to a .tmp path, then
os.replace -- an atomic rename on both POSIX and Windows) so a killed
process never leaves a half-written cache entry that a later run would
mistake for a valid one.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional


def _replace_with_retry(tmp_path: Path, path: Path, attempts: int = 5, delay: float = 0.05) -> None:
    """os.replace() is atomic on both POSIX and Windows, but on Windows
    it can transiently fail with WinError 5 ("Access is denied") when
    another process (commonly antivirus real-time scanning) briefly
    holds an open handle on a just-written temp file -- not a logic
    bug, a well-known OS-level race. Retried with a short backoff
    rather than failing the whole date's collection over a transient
    lock."""
    last_error = None
    for attempt in range(attempts):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(delay * (attempt + 1))
    raise last_error


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    _replace_with_retry(tmp_path, path)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(data)
    _replace_with_retry(tmp_path, path)


class RawCache:
    """One cache rooted at `directory`. `key` is any filesystem-safe
    string the caller constructs (e.g. "schedule_2025-06-15",
    "statcast_2025-06-15", "gamelog_pitching_543135_2025")."""

    def __init__(self, directory: Path):
        self.directory = directory

    def _payload_path(self, key: str, ext: str) -> Path:
        return self.directory / f"{key}.{ext}"

    def _meta_path(self, key: str) -> Path:
        return self.directory / f"{key}.meta.json"

    def has(self, key: str, ext: str) -> bool:
        return self._payload_path(key, ext).exists() and self._meta_path(key).exists()

    def read_text(self, key: str, ext: str) -> Optional[str]:
        path = self._payload_path(key, ext)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def read_meta(self, key: str) -> Optional[dict]:
        path = self._meta_path(key)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def write_text(self, key: str, ext: str, text: str, meta: dict) -> None:
        """Payload is written first, metadata second -- so a reader
        that only checks `has()` (both files present) never observes a
        payload without its metadata."""
        atomic_write_text(self._payload_path(key, ext), text)
        atomic_write_text(self._meta_path(key), json.dumps(meta, indent=2, default=str))

    def get_or_fetch_text(self, key: str, ext: str, fetch_fn, build_meta_fn, force: bool = False) -> str:
        """`fetch_fn() -> str` performs the live call; `build_meta_fn(text) -> dict`
        builds the metadata sidecar from the fetched text (so record
        counts etc. can be derived from the actual payload)."""
        if not force and self.has(key, ext):
            return self.read_text(key, ext)
        text = fetch_fn()
        self.write_text(key, ext, text, build_meta_fn(text))
        return text

    def get_or_fetch_json(self, key: str, fetch_fn, meta: dict, force: bool = False):
        """Milestone 32.1 regression guard for a real defect caught live
        during the full warehouse build: a cache payload can exist on
        disk (both `has()` checks pass) but contain corrupted/truncated
        content that isn't valid JSON -- confirmed live as a zero-filled
        weather cache file, almost certainly left by an abrupt process
        kill mid-write during an earlier interrupted run (the atomic
        rename in cache.py protects the FINAL path from ever holding a
        PARTIAL write, but not from an already-corrupted source write
        that completed and got renamed into place before the interrupt).
        Rather than trust an on-disk payload blindly, this SELF-HEALS:
        a JSONDecodeError on a cached read is treated exactly like a
        cache miss (silently re-fetch and overwrite), not a crash that
        aborts the whole date's collection. `fetch_fn() -> Any
        (JSON-serializable)` performs the live call; the result (even
        None) is cached via json.dumps."""
        if not force and self.has(key, "json"):
            text = self.read_text(key, "json")
            try:
                return json.loads(text) if text else None
            except json.JSONDecodeError:
                pass  # corrupted cache entry -- fall through and refetch, exactly like a miss
        value = fetch_fn()
        self.write_text(key, "json", json.dumps(value), meta)
        return value
