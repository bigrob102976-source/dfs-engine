"""MLB FILE LOCK / DUPLICATE ARTIFACT WRITER RACE -- real concurrency
regression tests, not sequential unit tests. Uses a threading.Barrier to
force two writer threads to call the SAME persistence entry point as
close to simultaneously as possible (real OS-level file I/O releases the
GIL, so this genuinely exercises the same race a live worker/duplicate-
process incident would -- confirmed live 2026-09-05: two orphaned
processes computing ownership for the same slate at the same second hit
exactly this path, one raising FileExistsError).

Covers two layers:
  1. The shared LocalArtifactStorage atomic-write primitive itself
     (research/artifact_storage.py::_atomic_write_bytes) -- proves the
     O_CREAT|O_EXCL path genuinely rejects a second concurrent creator
     with no corruption, and the temp-file+os.replace path never exposes
     a partially-written file.
  2. The real ownership writer that hit this live
     (ownership/persistence.py::save_ownership_document) -- proves the
     content-hash-qualified filename fix makes two concurrent writers of
     the IDENTICAL real result collapse safely (no crash, no
     corruption, no FileExistsError escaping), while two concurrent
     writers of genuinely DIFFERENT content never collide.
"""

import json
import threading
from pathlib import Path

import pytest

from config.ownership_config import OWNERSHIP_MODEL_VERSION
from ownership.model import build_ownership_projections
from ownership.persistence import build_ownership_document, save_ownership_document
from research.artifact_storage import LocalArtifactStorage
from tests._ownership_fixtures import small_slate_hitters, small_slate_pitchers


def _document(generated_at="2026-09-05T01:46:00+00:00", slate_id=None, posted_lineup_hitter_fraction=1.0):
    projections, team_pop, report = build_ownership_projections(small_slate_pitchers(), small_slate_hitters(), posted_lineup_hitter_fraction)
    return build_ownership_document(
        "2026-09-05", generated_at, OWNERSHIP_MODEL_VERSION, "dfs_input/2026-09-05/dk_player_pool_x.json",
        "predictions/2026-09-05/pitcher_board_x.json", "predictions/2026-09-05/batter_board_x.json",
        projections, team_pop, report, slate_id=slate_id,
    )


def _run_concurrently(fns):
    """Runs every callable in `fns` on its own thread, released
    simultaneously via a Barrier -- forces genuine concurrent execution
    (not just "called in a loop") for the duration of the real file I/O
    each callable performs. Returns (results, exceptions) lists in the
    same order as `fns`."""
    barrier = threading.Barrier(len(fns))
    results = [None] * len(fns)
    exceptions = [None] * len(fns)

    def worker(i, fn):
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 -- captured for the test to assert on, not swallowed
            exceptions[i] = exc

    threads = [threading.Thread(target=worker, args=(i, fn)) for i, fn in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, exceptions


class TestAtomicWritePrimitiveConcurrency:
    """Layer 1: the shared research/artifact_storage.py primitive itself."""

    def test_two_concurrent_no_overwrite_writers_for_the_same_key_one_wins_one_gets_a_clean_exception(self, tmp_path):
        storage = LocalArtifactStorage(tmp_path)
        results, exceptions = _run_concurrently([
            lambda: storage.write_json("shared_key.json", {"writer": "A"}, allow_overwrite=False),
            lambda: storage.write_json("shared_key.json", {"writer": "B"}, allow_overwrite=False),
        ])

        successes = [i for i, e in enumerate(exceptions) if e is None]
        failures = [i for i, e in enumerate(exceptions) if e is not None]
        # Exactly one writer wins (O_CREAT|O_EXCL is atomic at the OS
        # level -- there is no window where both could succeed).
        assert len(successes) == 1
        assert len(failures) == 1
        assert isinstance(exceptions[failures[0]], FileExistsError)

        # The persisted content is the WINNER's real, complete, valid
        # JSON -- never corrupted, never a mix of both writers' bytes.
        persisted = storage.read_json("shared_key.json")
        assert persisted in ({"writer": "A"}, {"writer": "B"})

    def test_two_concurrent_overwrite_allowed_writers_never_expose_a_partial_file(self, tmp_path):
        # allow_overwrite=True uses temp-file + os.replace -- a reader
        # can only ever observe one writer's COMPLETE bytes, never a
        # torn mix of both (this is the real risk plain open("w") had:
        # truncate-then-write is not atomic).
        storage = LocalArtifactStorage(tmp_path)
        big_a = {"writer": "A", "payload": "a" * 50_000}
        big_b = {"writer": "B", "payload": "b" * 50_000}
        _run_concurrently([
            lambda: storage.write_json("shared_key.json", big_a, allow_overwrite=True),
            lambda: storage.write_json("shared_key.json", big_b, allow_overwrite=True),
        ])

        persisted = storage.read_json("shared_key.json")
        assert persisted is not None, "read_json returned None -- the file was corrupted/unparseable"
        assert persisted in (big_a, big_b), "persisted content is a mix of both writers -- torn write"


class TestOwnershipWriterConcurrency:
    """Layer 2: the real ownership writer that hit this race live."""

    def test_two_concurrent_writers_of_the_identical_real_result_never_raise_and_never_corrupt(self, tmp_path):
        # The EXACT real incident: two duplicate/orphaned processes
        # computing the SAME real ownership result for the same slate
        # at the same second.
        doc = _document()
        results, exceptions = _run_concurrently([
            lambda: save_ownership_document(doc, "2026-09-05", "20260905T014611", output_root=tmp_path),
            lambda: save_ownership_document(doc, "2026-09-05", "20260905T014611", output_root=tmp_path),
        ])

        assert exceptions == [None, None], f"FileExistsError (or any exception) leaked to a caller: {exceptions}"
        assert results[0] == results[1], "both writers of identical content must resolve to the SAME immutable key"

        persisted = json.loads(results[0].read_text(encoding="utf-8"))
        assert persisted == doc

        # Exactly one real file on disk -- no duplicate/partial artifacts.
        written = list((tmp_path / "2026-09-05").glob("ownership_*.json"))
        assert len(written) == 1

    def test_two_concurrent_writers_of_genuinely_different_content_both_persist_without_collision(self, tmp_path):
        # SAME date/slate_id/timestamp -- the only difference is a real
        # input (posted_lineup_hitter_fraction), producing genuinely
        # different ownership numbers. This must never collide/overwrite,
        # even though it's the identical (date, timestamp, slate_id) key
        # prefix the old bug raced on.
        doc_a = _document(posted_lineup_hitter_fraction=1.0)
        doc_b = _document(posted_lineup_hitter_fraction=0.3)
        assert doc_a["players"] != doc_b["players"], "test fixture setup problem -- these must actually differ"

        results, exceptions = _run_concurrently([
            lambda: save_ownership_document(doc_a, "2026-09-05", "20260905T014611", output_root=tmp_path),
            lambda: save_ownership_document(doc_b, "2026-09-05", "20260905T014611", output_root=tmp_path),
        ])

        assert exceptions == [None, None]
        assert results[0] != results[1], "genuinely different content must never land at the same key"
        assert results[0].exists() and results[1].exists()
        persisted_a = json.loads(results[0].read_text(encoding="utf-8"))
        persisted_b = json.loads(results[1].read_text(encoding="utf-8"))
        assert persisted_a == doc_a
        assert persisted_b == doc_b
