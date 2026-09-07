"""NFL M2 -- immutable, timestamped persistence for the canonical NFL
player pool. Mirrors dfs/persistence.py's exact discipline (new file
every build, FileExistsError instead of silent clobber, routed through
research/storage.py's save_json -- the same sport-agnostic primitive
MLB's persistence already uses) but rooted at a sport-scoped path so an
NFL artifact can never collide with or be mistaken for an MLB one:

    dfs_input/nfl/
      YYYY-MM-DD/
        nfl_player_pool_<timestamp>.json

NFL M2 scope: local disk only (LocalArtifactStorage, the default when
OBJECT_STORAGE_* isn't configured) -- no production R2 writes, no
Railway/worker integration, per this milestone's explicit boundary.
"""

from pathlib import Path
from typing import List, Optional

from research.artifact_storage import ARTIFACT_ROOT, raise_if_exists, resolve_artifact_storage, to_artifact_key
from research.storage import save_json

from nfl.models import NflPoolBuildResult

DEFAULT_NFL_DFS_INPUT_ROOT = Path(__file__).resolve().parent.parent / "dfs_input" / "nfl"


def save_nfl_player_pool(result: NflPoolBuildResult, timestamp: str, output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT) -> Path:
    path = Path(output_root) / result.slate_date / f"nfl_player_pool_{timestamp}.json"
    raise_if_exists(path)
    save_json(path, result.to_dict())
    return path


def list_nfl_player_pools(slate_date: str, output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT) -> List[Path]:
    """Every saved NFL pool snapshot for a date, oldest first (filenames
    sort chronologically -- mirrors dfs/persistence.py::list_player_pools)."""
    folder = Path(output_root) / slate_date
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    keys = storage.list_files(to_artifact_key(folder), prefix="nfl_player_pool_", ext=".json")
    return [ARTIFACT_ROOT / key for key in keys]


def load_latest_nfl_player_pool(slate_date: str, output_root: Path = DEFAULT_NFL_DFS_INPUT_ROOT) -> Optional[dict]:
    pools = list_nfl_player_pools(slate_date, output_root)
    if not pools:
        return None
    path = pools[-1]
    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    return storage.read_json(to_artifact_key(path))
