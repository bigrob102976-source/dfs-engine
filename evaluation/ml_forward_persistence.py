"""Milestone 32.5 -- immutable, per-slate Big Money ML forward-results
documents. Mirrors big_money_ml/persistence.py's exact discipline: a
sibling top-level data directory, FileExistsError on any attempted
overwrite, timestamped filenames, never merged with any other slate's
document. Persisted by (date, slate_id) so multiple slates on the same
calendar date are never conflated -- "Do not overwrite prior slates."

    ml_forward_results/
      <date>/
        <slate_id>/
          ml_forward_results_<timestamp>.json
"""

import json
from pathlib import Path
from typing import List, Optional

from research.artifact_storage import raise_if_exists
from research.prediction_snapshot import timestamp_tag
from research.storage import save_json

DEFAULT_ML_FORWARD_RESULTS_ROOT = Path(__file__).resolve().parent.parent / "ml_forward_results"

_FILENAME_PREFIX = "ml_forward_results"


def _slate_folder(slate_date: str, slate_id: str, output_root: Path) -> Path:
    return Path(output_root) / slate_date / slate_id


def save_ml_forward_results_document(document: dict, output_root: Path = DEFAULT_ML_FORWARD_RESULTS_ROOT) -> Path:
    slate_date = document["slate_date"]
    slate_id = document["slate_id"]
    timestamp = timestamp_tag(document["generated_at"])
    path = _slate_folder(slate_date, slate_id, output_root) / f"{_FILENAME_PREFIX}_{timestamp}.json"

    # Milestone 33.2: storage-aware (see bluecollar/persistence.py's
    # identical comment for why this replaced a local path.exists() check).
    raise_if_exists(path)

    save_json(path, document)
    return path


def list_ml_forward_results_snapshots(slate_date: str, slate_id: str, output_root: Path = DEFAULT_ML_FORWARD_RESULTS_ROOT) -> List[Path]:
    folder = _slate_folder(slate_date, slate_id, output_root)
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{_FILENAME_PREFIX}_*.json"))


def load_latest_ml_forward_results(slate_date: str, slate_id: str, output_root: Path = DEFAULT_ML_FORWARD_RESULTS_ROOT) -> Optional[dict]:
    snapshots = list_ml_forward_results_snapshots(slate_date, slate_id, output_root)
    if not snapshots:
        return None
    with snapshots[-1].open("r", encoding="utf-8") as f:
        return json.load(f)


def list_all_ml_forward_results_slates(output_root: Path = DEFAULT_ML_FORWARD_RESULTS_ROOT) -> List[dict]:
    """Every (date, slate_id)'s LATEST forward-results document, sorted
    chronologically oldest-first by slate_date -- the raw material for
    cumulative forward-history windows (see ml_forward_history.py).
    Never reads an in-progress/partial document from a date whose folder
    doesn't exist yet -- a date with zero collection runs is simply
    absent, not a zero-filled placeholder."""
    root = Path(output_root)
    if not root.exists():
        return []
    slates: List[dict] = []
    for date_dir in sorted(root.iterdir()):
        if not date_dir.is_dir():
            continue
        for slate_dir in sorted(date_dir.iterdir()):
            if not slate_dir.is_dir():
                continue
            latest = load_latest_ml_forward_results(date_dir.name, slate_dir.name, output_root=root)
            if latest is not None:
                slates.append(latest)
    slates.sort(key=lambda d: (d.get("slate_date", ""), d.get("generated_at", "")))
    return slates
