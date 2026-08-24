"""Immutable, reproducible storage for Game Environment reports.
Mirrors research/prediction_snapshot.py's save discipline exactly:
every save writes a NEW timestamped file, nothing here ever opens an
existing snapshot file in write mode.

    game_environment_snapshots/
      YYYY-MM-DD/
        environment_<timestamp>.json

Milestone 33.2: routed through research/artifact_storage.py's
resolve_artifact_storage() (this module was one of the two confirmed
bypasses of that abstraction found by the M33.0 audit) -- local disk in
development, S3-compatible object storage in production, same as every
other persistence module in this project.
"""

import json
from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage, to_artifact_key
from research.prediction_snapshot import timestamp_tag

DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent.parent / "game_environment_snapshots"


def save_environment_report(document: dict, output_root: Path = DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT) -> Path:
    """`document` must already contain slate_date and generated_at
    (SlateEnvironmentReport.to_dict() always does)."""
    slate_date = document["slate_date"]
    ts = timestamp_tag(document["generated_at"])
    path = Path(output_root) / slate_date / f"environment_{ts}.json"
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    key = to_artifact_key(path)
    if storage.exists(key):
        raise FileExistsError(
            f"Refusing to overwrite existing immutable snapshot: {key}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )
    storage.write_json(key, document, allow_overwrite=False)
    return path


def list_environment_reports(slate_date: str, output_root: Path = DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    dir_key = to_artifact_key(folder)
    keys = storage.list_files(dir_key, prefix="environment_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_environment_report(slate_date: str, output_root: Path = DEFAULT_ENVIRONMENT_SNAPSHOT_ROOT) -> Optional[dict]:
    reports = list_environment_reports(slate_date, output_root)
    if not reports:
        return None
    return load_environment_report(reports[-1])


def load_environment_report(path: Path) -> dict:
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    result = storage.read_json(to_artifact_key(path))
    if result is None:
        # Preserve the old contract for a path that genuinely doesn't
        # resolve through the artifact store (e.g. a raw path passed
        # directly in a test) -- fall back to a direct read rather than
        # silently returning None where the caller expects a document.
        with Path(path).open("r", encoding="utf-8") as f:
            return json.load(f)
    return result
