"""Immutable, reproducible storage for external projection baselines and
Big Money adjusted projections. Mirrors research/prediction_snapshot.py's
save discipline exactly: every save writes a NEW timestamped file,
nothing here ever opens an existing snapshot file in write mode.

    external_projection_snapshots/
      YYYY-MM-DD/
        provider_<provider>_<timestamp>.json

    adjusted_projection_snapshots/
      YYYY-MM-DD/
        adjusted_<timestamp>.json
"""

import json
from pathlib import Path
from typing import List, Optional

from research.prediction_snapshot import timestamp_tag
from research.storage import save_json

DEFAULT_EXTERNAL_SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent / "external_projection_snapshots"
DEFAULT_ADJUSTED_SNAPSHOT_ROOT = Path(__file__).resolve().parent.parent / "adjusted_projection_snapshots"


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing immutable snapshot: {path}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )


# ----------------------------------------------------------------------------
# External baseline snapshots
# ----------------------------------------------------------------------------


def save_baseline_snapshot(document: dict, output_root: Path = DEFAULT_EXTERNAL_SNAPSHOT_ROOT) -> Path:
    """`document` must already contain slate_date, provider, and
    retrieved_at -- the filename timestamp is derived from retrieved_at
    so re-running the same second twice is refused rather than silently
    overwriting (see timestamp_tag)."""
    slate_date = document["slate_date"]
    provider = document["provider"]
    ts = timestamp_tag(document["retrieved_at"])
    path = Path(output_root) / slate_date / f"provider_{provider}_{ts}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def list_baseline_snapshots(slate_date: str, provider: Optional[str] = None, output_root: Path = DEFAULT_EXTERNAL_SNAPSHOT_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    pattern = f"provider_{provider}_*.json" if provider else "provider_*.json"
    return sorted(folder.glob(pattern))


def load_latest_baseline_snapshot(slate_date: str, provider: Optional[str] = None, output_root: Path = DEFAULT_EXTERNAL_SNAPSHOT_ROOT) -> Optional[dict]:
    snapshots = list_baseline_snapshots(slate_date, provider, output_root)
    if not snapshots:
        return None
    return load_snapshot(snapshots[-1])


# ----------------------------------------------------------------------------
# Big Money adjusted-projection snapshots
# ----------------------------------------------------------------------------


def save_adjusted_snapshot(document: dict, output_root: Path = DEFAULT_ADJUSTED_SNAPSHOT_ROOT) -> Path:
    """`document` must already contain slate_date and generated_at."""
    slate_date = document["slate_date"]
    ts = timestamp_tag(document["generated_at"])
    path = Path(output_root) / slate_date / f"adjusted_{ts}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def list_adjusted_snapshots(slate_date: str, output_root: Path = DEFAULT_ADJUSTED_SNAPSHOT_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob("adjusted_*.json"))


def load_latest_adjusted_snapshot(slate_date: str, output_root: Path = DEFAULT_ADJUSTED_SNAPSHOT_ROOT) -> Optional[dict]:
    snapshots = list_adjusted_snapshots(slate_date, output_root)
    if not snapshots:
        return None
    return load_snapshot(snapshots[-1])


def load_snapshot(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)
