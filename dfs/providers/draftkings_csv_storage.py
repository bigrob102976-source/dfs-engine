"""Storage for real DraftKings salary-export CSVs the user uploads
through the dashboard (Milestone 19) -- feeds
dfs/providers/draftkings_csv_provider.py.

Distinct from dfs/persistence.py::save_raw_csv, which stores a single
CSV alongside one immediate pool build for the older manual `--csv` CLI
path (scripts/build_dk_player_pool.py). An upload here is decoupled
from any specific pool build -- the provider re-reads whatever's on
disk on every refresh -- and there can be more than one per date, one
per real DraftKings slate type (Main/Turbo/Night/Late/Afternoon/
Showdown/...), each tagged with its slate label at upload time since
DraftKings' own CSV export has no field that names the slate.

    dfs_input/
      YYYY-MM-DD/
        uploaded_dk_slates/
          <slate_label>_<timestamp>.csv
          <slate_label>_<timestamp>.meta.json

Uploading the same slate label again (e.g. a late-swap re-export) never
overwrites the earlier one -- both are kept, and
draftkings_csv_provider.py always uses only the newest upload per label
(the same "newest wins" rule every other immutable snapshot in this
project already follows).
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from research.prediction_snapshot import timestamp_tag

DEFAULT_DFS_INPUT_ROOT = Path(__file__).resolve().parent.parent.parent / "dfs_input"
_SUBDIR = "uploaded_dk_slates"


@dataclass
class DraftKingsUpload:
    path: str
    meta_path: str
    slate_date: str
    slate_label: str
    original_filename: str
    uploaded_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing DraftKings CSV upload: {path}")


def _safe_label(slate_label: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in slate_label).strip("_")
    return cleaned or "slate"


def save_upload(
    csv_bytes: bytes, slate_date: str, slate_label: str, original_filename: str,
    output_root: Path = DEFAULT_DFS_INPUT_ROOT, uploaded_at: Optional[str] = None,
) -> DraftKingsUpload:
    """`uploaded_at` defaults to the real current time; callers can pass
    an explicit ISO timestamp (e.g. tests saving two uploads back to
    back) so two saves within the same wall-clock second still get
    distinct, non-colliding filenames -- timestamp_tag() only has
    second resolution, same as every other immutable snapshot type in
    this project."""
    dest_dir = Path(output_root) / slate_date / _SUBDIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    uploaded_at = uploaded_at or datetime.now(timezone.utc).isoformat()
    ts = timestamp_tag(uploaded_at)
    stem = f"{_safe_label(slate_label)}_{ts}"
    csv_path = dest_dir / f"{stem}.csv"
    meta_path = dest_dir / f"{stem}.meta.json"
    _no_overwrite(csv_path)
    _no_overwrite(meta_path)

    csv_path.write_bytes(csv_bytes)
    upload = DraftKingsUpload(
        path=str(csv_path), meta_path=str(meta_path), slate_date=slate_date,
        slate_label=slate_label, original_filename=original_filename, uploaded_at=uploaded_at,
    )
    meta_path.write_text(json.dumps(upload.to_dict(), indent=2), encoding="utf-8")
    return upload


def list_uploads(slate_date: str, output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> List[DraftKingsUpload]:
    """All uploads for `slate_date`, unfiltered (may include more than
    one per slate_label) -- callers that want "the current one per
    label" should dedupe by newest `uploaded_at` themselves (see
    draftkings_csv_provider.py). Skips any sidecar that fails to parse
    rather than failing the whole listing."""
    dest_dir = Path(output_root) / slate_date / _SUBDIR
    if not dest_dir.exists():
        return []
    uploads = []
    for meta_path in sorted(dest_dir.glob("*.meta.json")):
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            uploads.append(DraftKingsUpload(**data))
        except (OSError, ValueError, TypeError):
            continue
    return uploads


def delete_upload(csv_path: str, output_root: Path = DEFAULT_DFS_INPUT_ROOT) -> None:
    """Removes one uploaded CSV and its metadata sidecar. Refuses
    anything outside dfs_input/<date>/uploaded_dk_slates/ -- mirrors
    external_projections/csv_import/history.py's ownership check."""
    resolved = Path(csv_path).resolve()
    root = Path(output_root).resolve()
    if _SUBDIR not in resolved.parts:
        raise ValueError(f"Not an uploaded DraftKings CSV: {csv_path}")
    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise ValueError(f"Path is not inside the DFS input root: {csv_path}") from e

    meta_path = resolved.with_name(resolved.stem + ".meta.json")
    if resolved.exists():
        resolved.unlink()
    if meta_path.exists():
        meta_path.unlink()
