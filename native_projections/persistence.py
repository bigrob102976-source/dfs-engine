"""Immutable Native Projection snapshots -- copies
research/prediction_snapshot.py's save/list/load pattern exactly (new
file per generation, `FileExistsError` if a path already exists, nothing
here ever opens an existing snapshot in write mode).

--------------------------------------------------------------------------
Snapshot root naming
--------------------------------------------------------------------------
The milestone's own spec text names the path
"native_projections/YYYY-MM-DD/native_projection_<timestamp>.json". Taken
completely literally that would put JSON data files inside the
native_projections/ PYTHON PACKAGE directory itself -- but every other
persistence module in this codebase (research/prediction_snapshot.py ->
predictions/, projection_engine/persistence.py -> ai_projection_snapshots/,
external_projections/persistence.py -> external_projection_snapshots/,
research/game_environment/storage.py -> game_environment_snapshots/) uses
a SIBLING top-level data directory with a name distinct from its owning
code package, specifically so data files never get mixed into a Python
package directory. This module follows that established, universal
convention instead: native_projection_snapshots/ (a name already reserved
in dashboard/lib/artifactRoot.ts's ARTIFACT_DIRS for this exact purpose).

--------------------------------------------------------------------------
Point-in-time integrity
--------------------------------------------------------------------------
Every saved document records model_version and generated_at (see
native_projections/models.py::NativeProjectionDocument) so it's always
possible to determine exactly which model version and what data existed
at generation time -- consistent with CLAUDE.md's evaluation requirements.
"""

import json
from pathlib import Path
from typing import List

from research.prediction_snapshot import timestamp_tag
from research.storage import save_json

from native_projections.models import NativeProjectionDocument

DEFAULT_NATIVE_PROJECTION_ROOT = Path(__file__).resolve().parent.parent / "native_projection_snapshots"

_FILENAME_PREFIX = "native_projection"


def save_native_projection_document(
    document: NativeProjectionDocument, output_root: Path = DEFAULT_NATIVE_PROJECTION_ROOT
) -> Path:
    slate_date = document.slate_date
    timestamp = timestamp_tag(document.generated_at)
    path = Path(output_root) / slate_date / f"{_FILENAME_PREFIX}_{timestamp}.json"

    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing immutable native projection snapshot: {path}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )

    save_json(path, document.to_dict())
    return path


def list_native_projection_snapshots(slate_date: str, output_root: Path = DEFAULT_NATIVE_PROJECTION_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{_FILENAME_PREFIX}_*.json"))


def load_latest_native_projection_snapshot(slate_date: str, output_root: Path = DEFAULT_NATIVE_PROJECTION_ROOT) -> dict:
    snapshots = list_native_projection_snapshots(slate_date, output_root)
    if not snapshots:
        raise FileNotFoundError(f"No native projection snapshots found for {slate_date} under {output_root}/")
    return load_native_projection_snapshot(snapshots[-1])


def load_native_projection_snapshot(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)
