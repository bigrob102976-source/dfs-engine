"""Milestone 32.2B -- immutable Big Money ML projection snapshots.
Mirrors native_projections/persistence.py exactly: a sibling top-level
data directory (never inside this Python package), FileExistsError on
any attempted overwrite, no snapshot ever opened in write mode."""

import json
from pathlib import Path
from typing import List, Optional

from research.prediction_snapshot import timestamp_tag
from research.storage import save_json

from big_money_ml.models import MLProjectionDocument

DEFAULT_ML_PROJECTION_ROOT = Path(__file__).resolve().parent.parent / "ml_projection_snapshots"

_FILENAME_PREFIX = "ml_projection"


def save_ml_projection_document(document: MLProjectionDocument, output_root: Path = DEFAULT_ML_PROJECTION_ROOT) -> Path:
    slate_date = document.slate_date
    timestamp = timestamp_tag(document.generated_at)
    path = Path(output_root) / slate_date / f"{_FILENAME_PREFIX}_{timestamp}.json"

    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing immutable Big Money ML projection snapshot: {path}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )

    save_json(path, document.to_dict())
    return path


def list_ml_projection_snapshots(slate_date: str, output_root: Path = DEFAULT_ML_PROJECTION_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{_FILENAME_PREFIX}_*.json"))


def load_latest_ml_projection_snapshot(slate_date: str, output_root: Path = DEFAULT_ML_PROJECTION_ROOT) -> Optional[dict]:
    snapshots = list_ml_projection_snapshots(slate_date, output_root)
    if not snapshots:
        return None
    return load_ml_projection_snapshot(snapshots[-1])


def load_ml_projection_snapshot(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)
