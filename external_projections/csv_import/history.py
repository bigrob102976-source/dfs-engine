"""Import History operations (Milestone 18): list, reactivate, and
delete CSV-imported baseline snapshots. Every immutable snapshot file
stays exactly as external_projections/persistence.py already writes it
-- "reactivating" an older import never edits or overwrites it; it
writes a brand-new, newer-timestamped copy, so whichever snapshot is
literally the newest file is naturally the one
load_latest_baseline_snapshot() (and therefore the optimizer) picks up.
That "newest wins" rule is the existing framework's only notion of
"active" -- this module doesn't add a separate active flag/database, it
just gives the user a button that produces a fresh copy.

Only snapshots this importer itself wrote (document["source"] ==
"csv_import") are ever listed, reactivated, or deleted here -- a
provider-fetched (mock/live BlueCollar) baseline is never touched by
the Import History UI.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from external_projections.persistence import (
    DEFAULT_EXTERNAL_SNAPSHOT_ROOT,
    list_baseline_snapshots,
    load_snapshot,
    save_baseline_snapshot,
)

_NAME_PATTERN_PREFIX = "provider_"


def list_imports(slate_date: str, output_root: Path = DEFAULT_EXTERNAL_SNAPSHOT_ROOT) -> List[dict]:
    all_snapshots = list_baseline_snapshots(slate_date, provider=None, output_root=output_root)
    active_path = all_snapshots[-1] if all_snapshots else None

    entries: List[dict] = []
    for path in all_snapshots:
        try:
            doc = load_snapshot(path)
        except (OSError, ValueError):
            continue
        if doc.get("source") != "csv_import":
            continue
        validation = doc.get("validation_summary") or {}
        entries.append({
            "path": str(path),
            "slate_date": doc.get("slate_date"),
            "provider": doc.get("provider"),
            "provider_name": doc.get("provider_name"),
            "original_filename": doc.get("original_filename"),
            "retrieved_at": doc.get("retrieved_at"),
            "player_count": doc.get("player_count"),
            "matched": validation.get("matched"),
            "unmatched": validation.get("unmatched"),
            "ambiguous": validation.get("ambiguous"),
            "is_active": path == active_path,
        })
    entries.sort(key=lambda e: e["retrieved_at"] or "", reverse=True)
    return entries


def _validate_owned_path(path: Path, output_root: Path) -> dict:
    resolved = Path(path).resolve()
    root = Path(output_root).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise ValueError(f"Path is not inside the external projection snapshot root: {path}") from e
    if not resolved.name.startswith(_NAME_PATTERN_PREFIX) or not resolved.name.endswith(".json"):
        raise ValueError(f"Not a projection baseline snapshot file: {path}")

    doc = load_snapshot(resolved)
    if doc.get("source") != "csv_import":
        raise ValueError("Only CSV-imported snapshots can be managed from Import History.")
    return doc


def reactivate_import(path: str, output_root: Path = DEFAULT_EXTERNAL_SNAPSHOT_ROOT) -> str:
    """Writes a new, newer-timestamped copy of `path`'s content so it
    becomes the newest snapshot for its slate date again -- see module
    docstring. Returns the new file's path as a string."""
    doc = _validate_owned_path(Path(path), Path(output_root))
    new_doc = dict(doc)
    new_doc["retrieved_at"] = datetime.now(timezone.utc).isoformat()
    new_doc["reactivated_from"] = str(path)
    new_path = save_baseline_snapshot(new_doc, output_root=output_root)
    return str(new_path)


def delete_import(path: str, output_root: Path = DEFAULT_EXTERNAL_SNAPSHOT_ROOT) -> None:
    resolved = Path(path).resolve()
    _validate_owned_path(resolved, Path(output_root))
    resolved.unlink()
