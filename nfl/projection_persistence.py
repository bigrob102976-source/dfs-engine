"""NFL M4 -- immutable, timestamped persistence for Big Money Native NFL
projection snapshots. Mirrors nfl/persistence.py's (M2) exact discipline
-- new file every save, FileExistsError instead of silent clobber,
routed through research/storage.py's save_json.

Sport- and source-isolated path, never colliding with MLB or with a
future external-benchmark artifact:

    projections/nfl/big_money_native/
      YYYY-MM-DD/
        {draft_group_id}/
          nfl_projection_<timestamp>.json

EXTERNAL_BENCHMARK_ROOT is defined (reserved) but nothing in NFL M4
writes to it -- see this milestone's explicit product decision that
FantasyPros/BlueCollar are dev/admin-only benchmarks, never mixed into
the Big Money Native namespace. No fetcher for it exists yet.

NFL M4 scope: local disk only -- no production R2 writes.
"""

from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.projection_models import NflProjectionSnapshot

DEFAULT_BIG_MONEY_NATIVE_ROOT = Path(__file__).resolve().parent.parent / "projections" / "nfl" / "big_money_native"

# Reserved for a future external-benchmark fetcher (FantasyPros/
# BlueCollar) -- deliberately never written to by this module or any
# NFL M4 code, kept structurally separate from Big Money Native's own
# artifacts per this milestone's isolation requirement.
EXTERNAL_BENCHMARK_ROOT = Path(__file__).resolve().parent.parent / "projections" / "nfl" / "external_benchmark"


def save_nfl_projection_snapshot(snapshot: NflProjectionSnapshot, timestamp: str, output_root: Path = DEFAULT_BIG_MONEY_NATIVE_ROOT) -> Path:
    path = Path(output_root) / snapshot.slate_date / str(snapshot.draft_group_id) / f"nfl_projection_{timestamp}.json"
    raise_if_exists(path)
    save_json(path, snapshot.to_dict())
    return path


def list_nfl_projection_snapshots(slate_date: str, draft_group_id: int, output_root: Path = DEFAULT_BIG_MONEY_NATIVE_ROOT) -> List[Path]:
    folder = Path(output_root) / slate_date / str(draft_group_id)
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_projection_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_nfl_projection_snapshot(slate_date: str, draft_group_id: int, output_root: Path = DEFAULT_BIG_MONEY_NATIVE_ROOT) -> Optional[dict]:
    snapshots = list_nfl_projection_snapshots(slate_date, draft_group_id, output_root)
    if not snapshots:
        return None
    path = snapshots[-1]
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(path))
